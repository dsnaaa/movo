import platform
import ctypes
import time
import threading
from pynput.mouse import Controller, Button
from pynput.keyboard import Controller as KeyController, Key

# macOS 兼容性补丁：处理某些 pyobjc 版本缺失 CGDisplayPixelsHigh 的问题
if platform.system() == 'Darwin':
    try:
        import Quartz
        if not hasattr(Quartz, 'CGDisplayPixelsHigh'):
            def CGDisplayPixelsHigh(display_id):
                return int(Quartz.CGDisplayBounds(display_id).size.height)
            Quartz.CGDisplayPixelsHigh = CGDisplayPixelsHigh
    except Exception:
        pass

mouse = Controller()

def wake_up_cursor():
    if platform.system() == 'Windows':
        MOUSEEVENTF_MOVE = 0x0001
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, 1, 1, 0, 0)
        time.sleep(0.01)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, -1, -1, 0, 0)

# 唤醒节流：wake_up_cursor 里有两次 mouse_event + 10ms sleep，每次移动都调的话
# 等于给每个 move 事件硬加 10ms 延迟，触控板会明显发滞。只在「闲了一阵子之后的
# 第一次移动」唤醒一次就够（目的是把系统/显示器从休眠态叫起来，不是每帧都要）。
_WAKE_INTERVAL = 30.0
_last_wake = 0.0


def handle_move(data):
    mouse.move(data['dx'], data['dy'])
    global _last_wake
    now = time.time()
    if now - _last_wake >= _WAKE_INTERVAL:
        _last_wake = now
        wake_up_cursor()

def handle_click(data):
    button_type = data.get('button')
    if button_type == 'left':
        mouse.click(Button.left)
    elif button_type == 'right':
        mouse.click(Button.right)
    elif button_type == 'middle':
        mouse.click(Button.middle)
    elif button_type == 'x1':
        mouse.click(Button.x1)
    elif button_type == 'x2':
        mouse.click(Button.x2)

def handle_drag_start():
    _press(Button.left)

def handle_drag_end():
    _release(Button.left, 'drag_end')

def handle_mid_down():
    _press(Button.middle)

def handle_mid_up():
    _release(Button.middle, 'mid_up')


# ---------------------------------------------------------------------------
# 按住状态兜底：手机端 touchend 丢了（切后台、页面重载、App 被杀）就会留下
# “一直按着”的键 —— 左键按住时表现为“点什么都没反应 / 变成拖选”，
# 中键按住时 Windows 会直接吞掉左右键点击（这就是“鼠标失灵”的真身）。
# 因此这里统一记账，并提供 release_all() 与超时看门狗。
# ---------------------------------------------------------------------------

_held = {}            # Button -> 按下时刻
_held_lock = threading.Lock()
_MIDDLE_MAX_HOLD = 5.0   # 中键不需要长按，超过 5 秒一定是漏了 up
_LEFT_MAX_HOLD = 60.0    # 拖拽是合法长按，只兜极端情况

# 用来向系统查询「这个键此刻到底是不是按着」的虚拟键码
_VK_CODE = {
    Button.left: 0x01,    # VK_LBUTTON
    Button.right: 0x02,   # VK_RBUTTON
    Button.middle: 0x04,  # VK_MBUTTON
}

_logger = None


def set_logger(fn):
    """由 server.py 注入诊断日志（写 _diag.log）。"""
    global _logger
    _logger = fn


def _log(msg):
    if _logger is None:
        return
    try:
        _logger('[mouse] ' + msg)
    except Exception:
        pass


def _is_down(btn):
    """系统层面这个键此刻是否真的处于按下状态。

    没按着的时候绝对不能调 release —— 实测（_probe_release.py）即使键没按下，
    pynput 也会老老实实往系统塞一个 UP 事件。这个"孤儿 UP"落到前台窗口上，
    窗口收到 WM_RBUTTONUP 就直接弹右键菜单（很多窗口根本不校验 DOWN）。
    这就是"手什么都没动，过一会儿自己冒出右键"的真凶：
    手机 socket 每断一次线（切前台/锁屏/心跳重连/换页），
    server 的 handle_disconnect 就调 release_all()，凭空放出一个右键 UP。
    """
    vk = _VK_CODE.get(btn)
    if vk is not None and platform.system() == 'Windows':
        try:
            return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
        except Exception:
            pass
    return True   # 其它平台 / 查询失败：保守地沿用旧行为


def _press(btn):
    # 按下之前先确保是干净状态。只有真的按着才松，否则又是一颗孤儿 UP。
    if btn in _held or _is_down(btn):
        _release(btn, 'pre-press')
    with _held_lock:
        _held[btn] = time.time()
    mouse.press(btn)


def _release(btn, reason=''):
    """松开按键；已经没按着就什么都不做，返回 False。"""
    with _held_lock:
        held = btn in _held
    if not held and not _is_down(btn):
        return False
    try:
        mouse.release(btn)
    finally:
        with _held_lock:
            _held.pop(btn, None)
    if reason:
        _log('release %s (%s)' % (btn, reason))
    return True


def release_all(reason=''):
    """把可能还按着的键松开，用于连接建立/断开、启动自检。

    只松「真的按着」的键 —— 见 _is_down 的说明，多松一次就是一次幽灵点击。
    """
    done = []
    for btn in (Button.left, Button.middle, Button.right):
        try:
            if _release(btn, reason):
                done.append(str(btn))
        except Exception:
            pass
    with _held_lock:
        _held.clear()
    if done:
        _log('release_all(%s): %s' % (reason, ', '.join(done)))


def _watchdog():
    while True:
        time.sleep(1.0)
        now = time.time()
        expired = []
        with _held_lock:
            for btn, ts in list(_held.items()):
                limit = _MIDDLE_MAX_HOLD if btn == Button.middle else _LEFT_MAX_HOLD
                if now - ts > limit:
                    expired.append(btn)
        # 交给 _release 处理：它记账里还有这个键，必定会真的松开
        for btn in expired:
            try:
                _release(btn, 'watchdog-timeout')
            except Exception:
                pass


threading.Thread(target=_watchdog, daemon=True, name='mouse-watchdog').start()

def handle_scroll(data):
    # dx: 水平, dy: 垂直
    dx = data.get('dx', 0)
    dy = data.get('dy', 0)
    
    # macOS 滚动方向通常与 Windows 相反
    if platform.system() == 'Darwin':
        mouse.scroll(-dx, -dy)
    else:
        mouse.scroll(dx, dy)


# ---------- 双指捏合：Ctrl(或 macOS Cmd) + 滚轮 ----------
_kb = KeyController()


def handle_zoom(data):
    """双指捏合 → Ctrl + 滚一格，等价于应用里的 Ctrl+滚轮缩放。

    顺序必须严格是 ctrl down → wheel → ctrl up：多数应用是靠
    GetKeyState(VK_CONTROL) 判断这次滚轮该不该缩放，先滚后按完全没反应。
    这里用 pressed() 上下文，异常时也会抬起修饰键，不会把 Ctrl 卡在按下状态。
    """
    try:
        steps = int(data.get('steps') or 1)
    except (TypeError, ValueError):
        steps = 1
    steps = max(1, min(6, steps))          # 一次最多 6 档，防止误触手抖放大过头

    try:
        direction = float(data.get('dir', 1) or 0)
    except (TypeError, ValueError):
        direction = 1
    sign = -1 if direction < 0 else 1

    is_mac = platform.system() == 'Darwin'
    modifier = Key.cmd if is_mac else Key.ctrl

    try:
        with _kb.pressed(modifier):
            # 应用是靠消息队列里的 WM_MOUSEWHEEL 去查 VK_CONTROL 状态的，
            # 抬起太快会读到「没按」→ 这次滚轮就变成普通滚动了，留点余量。
            time.sleep(0.014)
            for _ in range(steps):
                # macOS 的 scroll 方向与 Windows 相反
                mouse.scroll(0, -sign if is_mac else sign)
                # 两档之间留一点间隔，太密会被应用合并成一次，缩放就"吃档"了
                time.sleep(0.010)
            time.sleep(0.012)
    except Exception as e:
        _log('zoom error: %s' % e)
