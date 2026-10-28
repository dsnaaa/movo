"""系统级动作：屏幕亮度、打开终端、关机。

键盘页顶部那一排功能键走这里（音量/静音仍由 keyboard_service 走多媒体键）。

亮度的现实约束（这台机器实测过）：
  - DDC/CI（真背光，VCP 0x10）在这台小米电视上返回 ERROR_GEN_FAILURE，
    也就是显示器不认这条控制通道；换成笔记本内屏或支持 DDC 的显示器就能用。
  - 所以做两级：先试 DDC/CI，失败自动退到 gamma ramp 软件压暗。
    软件压暗不会改变电视背光，只是把输出的亮度曲线压下来，肉眼效果就是变暗，
    任何显示器都能用，是这里真正生效的那条路。
  - gamma 下限钳在 30%，避免把屏幕调成全黑找不回来；进程退出时还原原始曲线。
"""

import atexit
import ctypes
import os
import shutil
import subprocess
import sys
import threading
from ctypes import wintypes
from urllib.parse import urlsplit

IS_WINDOWS = sys.platform == 'win32'

# ============================ 亮度：DDC/CI ============================

class _PhysicalMonitor(ctypes.Structure):
    _fields_ = [('hPhysicalMonitor', wintypes.HANDLE),
                ('szPhysicalMonitorDescription', wintypes.WCHAR * 128)]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)


class _Ddc:
    """DDC/CI 亮度。显示器/显卡不支持时 supported 保持 False，调用方走 gamma。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._probed = False
        self._supported = False
        self._handles = []

    def _probe(self):
        try:
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            dxva2 = ctypes.WinDLL('dxva2', use_last_error=True)

            monitors = []
            user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(
                lambda h, hdc, r, d: (monitors.append(h), True)[1]), 0)

            for hm in monitors:
                count = wintypes.DWORD(0)
                if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
                        hm, ctypes.byref(count)) or count.value == 0:
                    continue
                arr = (_PhysicalMonitor * count.value)()
                if not dxva2.GetPhysicalMonitorsFromHMONITOR(hm, count.value, arr):
                    continue
                for pm in arr:
                    cur, mx = wintypes.DWORD(0), wintypes.DWORD(0)
                    ok = dxva2.GetMonitorBrightness(
                        pm.hPhysicalMonitor, None, ctypes.byref(cur), ctypes.byref(mx))
                    # ok 且 max > 0 才算真能调；否则这台显示器只是"存在"而已
                    if ok and mx.value > 0:
                        self._handles.append(pm.hPhysicalMonitor)
                    else:
                        try:
                            dxva2.DestroyPhysicalMonitor(pm.hPhysicalMonitor)
                        except Exception:
                            pass

            self._supported = bool(self._handles)
            self._dxva2 = dxva2
        except Exception:
            self._supported = False
        finally:
            self._probed = True

    def step(self, delta):
        """返回 True 表示 DDC 真的改动了背光。"""
        with self._lock:
            if not self._probed:
                self._probe()
            if not self._supported:
                return False
            changed = False
            for h in self._handles:
                try:
                    cur, mx = wintypes.DWORD(0), wintypes.DWORD(0)
                    if not self._dxva2.GetMonitorBrightness(
                            h, None, ctypes.byref(cur), ctypes.byref(mx)) or mx.value == 0:
                        continue
                    step = max(1, mx.value // 25)
                    target = max(0, min(mx.value, cur.value + delta * step))
                    if target == cur.value:
                        continue
                    if self._dxva2.SetMonitorBrightness(h, target):
                        changed = True
                except Exception:
                    continue
            return changed

    def level(self):
        with self._lock:
            if not self._supported:
                return None
            for h in self._handles:
                try:
                    cur, mx = wintypes.DWORD(0), wintypes.DWORD(0)
                    if self._dxva2.GetMonitorBrightness(
                            h, None, ctypes.byref(cur), ctypes.byref(mx)) and mx.value:
                        return round(cur.value / mx.value * 100)
                except Exception:
                    continue
            return None


# ============================ 亮度：gamma ============================

_GAMMA_MIN = 0.30          # 最低 30%，再低就真看不见了
_GAMMA_STEP = 0.08
_GAMMA_MAX = 1.00


class _Gamma:
    """用 SetDeviceGammaRamp 压输出亮度。get/set 都是整屏（主显示器）生效。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._level = 1.0
        self._orig = None
        self._ok = False
        if not IS_WINDOWS:
            return
        try:
            self._gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
            self._user32 = ctypes.WinDLL('user32', use_last_error=True)
            ramp = self._read_raw()
            if ramp is not None:
                self._orig = ramp
                self._ok = True
                atexit.register(self.restore)
                self._heal(ramp)
        except Exception:
            self._ok = False

    def _heal(self, ramp):
        """上一次如果是被强杀的（taskkill /f 走不到 atexit），曲线会停在调暗的状态，
        下次开机还是暗的。这里发现白点不到 65535 就当成"残留"，直接归位到 100%。"""
        if ramp[255] >= 65530:
            return
        if self._write_level(1.0):
            self._orig = self._read_raw() or self._orig

    # ---- 原始读写 ----
    def _read_raw(self):
        """读当前曲线，存成 768 个整数，退出时原样写回去。"""
        try:
            dc = self._user32.GetDC(None)
            if not dc:
                return None
            try:
                ramp = (wintypes.WORD * 256 * 3)()
                if self._gdi32.GetDeviceGammaRamp(dc, ctypes.byref(ramp)):
                    return [ramp[ch][i] for ch in range(3) for i in range(256)]
            finally:
                self._user32.ReleaseDC(None, dc)
        except Exception:
            pass
        return None

    def _write_level(self, level):
        try:
            dc = self._user32.GetDC(None)
            if not dc:
                return False
            try:
                ramp = (wintypes.WORD * 256 * 3)()
                for ch in range(3):
                    for i in range(256):
                        # 线性压缩：整体等比降低，观感接近调低背光，不会偏色
                        ramp[ch][i] = int(max(0, min(65535, i / 255.0 * 65535 * level)))
                return bool(self._gdi32.SetDeviceGammaRamp(dc, ctypes.byref(ramp)))
            finally:
                self._user32.ReleaseDC(None, dc)
        except Exception:
            return False

    # ---- 对外 ----
    def step(self, delta):
        with self._lock:
            if not self._ok:
                return False
            level = max(_GAMMA_MIN, min(_GAMMA_MAX, self._level + delta * _GAMMA_STEP))
            if abs(level - self._level) < 1e-6:
                return False
            if self._write_level(level):
                self._level = level
                return True
            return False

    def restore(self):
        with self._lock:
            if not self._ok or self._orig is None:
                return
            try:
                dc = self._user32.GetDC(None)
                if not dc:
                    return
                try:
                    ramp = (wintypes.WORD * 256 * 3)()
                    for i, v in enumerate(self._orig):
                        ramp[i // 256][i % 256] = v
                    self._gdi32.SetDeviceGammaRamp(dc, ctypes.byref(ramp))
                finally:
                    self._user32.ReleaseDC(None, dc)
                self._level = 1.0
            except Exception:
                pass

    @property
    def level(self):
        return round(self._level * 100)


# ============================ 对外接口 ============================

_ddc = _Ddc()
_gamma = _Gamma()
_bright_lock = threading.Lock()


def brightness(delta):
    """delta = +1 / -1；一次调一档。返回实际生效的方式，方便排查。"""
    with _bright_lock:
        if _ddc.step(delta):
            return 'ddc'
        if _gamma.step(delta):
            return 'gamma'
        return 'none'


def brightness_level():
    lv = _ddc.level()
    if lv is not None:
        return lv
    return _gamma.level


def restore_brightness():
    try:
        _gamma.restore()
    except Exception:
        pass


# ============================ 终端 ============================

def open_terminal():
    """按优先级拉起终端：Windows Terminal → PowerShell → cmd。
    pythonw 起的进程没有控制台，所以必须给新进程单独开一个控制台窗口。"""
    if not IS_WINDOWS:
        return False

    home = os.path.expanduser('~')
    candidates = []
    wt = shutil.which('wt.exe') or shutil.which('wt')
    if wt:
        # -d 起始目录，-- 之后的参数交给默认 profile
        candidates.append([wt, '-d', home])
    ps = shutil.which('powershell.exe') or shutil.which('powershell')
    if ps:
        candidates.append([ps, '-NoLogo', '-NoExit'])
    comspec = os.environ.get('COMSPEC') or shutil.which('cmd.exe')
    if comspec:
        candidates.append([comspec, '/k'])

    flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
    for cmd in candidates:
        try:
            subprocess.Popen(cmd, cwd=home, creationflags=flags, close_fds=True)
            return True
        except Exception:
            continue
    return False


# ============================ 浏览器 / 媒体键 ============================

DEFAULT_MEDIA_URL = 'https://www.bilibili.com'

# Chrome 优先，找不到退 Edge，再退系统默认浏览器
_CHROME_PATHS = (
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
    os.path.join(os.environ.get('PROGRAMFILES', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
)


def find_browser():
    exe = shutil.which('chrome.exe')
    if exe:
        return exe
    for p in _CHROME_PATHS:
        if p and os.path.exists(p):
            return p
    return None


def normalize_url(url):
    """手机端可能只写个 bilibili.com，补协议；只放行 http/https，
    免得被塞 file:// 之类在本机执行东西。"""
    u = str(url or '').strip() or DEFAULT_MEDIA_URL
    if '://' not in u:
        u = 'https://' + u
    p = urlsplit(u)
    if p.scheme.lower() not in ('http', 'https') or not p.netloc:
        raise ValueError('网址不合法')
    return u


def open_url(url):
    if not IS_WINDOWS:
        return False
    u = normalize_url(url)
    exe = find_browser()
    if exe:
        subprocess.Popen([exe, u], close_fds=True)
        return True
    os.startfile(u)          # 退到默认浏览器
    return True


# ============================ 关机 ============================

def shutdown(delay=3):
    """延迟几秒再关：手机端已经从长按确认过，这里给一点点余量。
    想取消就 `shutdown /a`。"""
    if not IS_WINDOWS:
        return False
    try:
        subprocess.Popen(['shutdown', '/s', '/t', str(int(delay))],
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                         close_fds=True)
        return True
    except Exception:
        return False


ACTIONS = {
    'bright_up': lambda: brightness(+1),
    'bright_down': lambda: brightness(-1),
    'terminal': open_terminal,
    'shutdown': shutdown,
}


def handle_action(name, url=None):
    """返回一句给手机端 toast 用的结果说明。"""
    name = str(name or '').strip().lower()

    if name in ('open_url', 'media', 'browser'):
        try:
            ok = open_url(url)
        except Exception as e:
            return {'ok': False, 'msg': str(e)[:60]}
        return {'ok': bool(ok), 'msg': '已在电脑打开'}

    if name in ('vol_up', 'volume_up'):
        from keyboard_service import handle_tap
        handle_tap({'key': 'volumeup'})
        return {'ok': True}
    if name in ('vol_down', 'volume_down'):
        from keyboard_service import handle_tap
        handle_tap({'key': 'volumedown'})
        return {'ok': True}
    if name in ('mute', 'vol_mute', 'volumemute'):
        from keyboard_service import handle_tap
        handle_tap({'key': 'volumemute'})
        return {'ok': True}

    fn = ACTIONS.get(name)
    if fn is None:
        return {'ok': False, 'msg': 'unknown action'}
    try:
        result = fn()
    except Exception as e:
        return {'ok': False, 'msg': str(e)[:60]}

    if name in ('bright_up', 'bright_down'):
        return {'ok': result != 'none', 'via': result, 'level': brightness_level()}
    return {'ok': bool(result)}
