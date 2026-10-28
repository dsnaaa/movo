import platform
import os
import sys
import subprocess
import tempfile
import threading
import time
import webbrowser

# 打包成无控制台 exe（或从 cmd 启动）时，标准输出是系统 ANSI 编码（中文 Windows 为 GBK），
# 下面 banner 里的 emoji 会抛 UnicodeEncodeError 直接把进程带走。统一改 UTF-8 并容错。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# macOS 隐藏 Dock 图标逻辑
if platform.system() == 'Darwin':
    try:
        from AppKit import NSBundle, NSApplication, NSApplicationActivationPolicyProhibited
        bundle = NSBundle.mainBundle()
        if bundle:
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            if info:
                info['LSUIElement'] = '1'
        # 立即锁定激活策略，防止 Dock 栏图标跳跃或显示
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyProhibited)
    except Exception:
        # 如果没有安装相应的库或环境不支持，静默失败
        pass

from web_app import app, socketio, get_all_ip_addresses
from flask import request
from flask_socketio import emit
from app_paths import app_dir, is_frozen, resource_path
import mouse_service
import keyboard_service
import system_service
import config_manager
import gamepad_service
import voice_service
import welcome_server

PORT = 5888
# Ensure relative config/log paths stay next to the executable.
os.chdir(app_dir())

# 启动手柄后台服务 (如果已安装 inputs)
gamepad_service.start_threads()

# 语音模型在后台加载（约 5 秒），不阻塞服务启动；页面会先显示“加载模型…”
voice_service.load_async()

def status_thread():
    """手柄状态广播：只在状态变化时发。

    之前是每秒无脑 emit 一次给所有连接 —— 手机那边白白收流量，WebView 也跟着被唤醒。
    现在按变化推送 + 30 秒兜底重发一次（兜底是给中途才打开页面的客户端补状态）。
    """
    last = None
    idle = 0
    while True:
        cur = (bool(gamepad_service.gamepad_connected), gamepad_service.gamepad_name)
        if cur != last or idle >= 30:
            last = cur
            idle = 0
            socketio.emit('gp_status', {'connected': cur[0], 'name': cur[1]})
        idle += 1
        time.sleep(1)

threading.Thread(target=status_thread, daemon=True).start()


def hide_console_window():
    """Hide the attached console window on Windows when launched via python.exe."""
    if platform.system() != 'Windows':
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def open_page(path='/'):
    webbrowser.open(f'https://127.0.0.1:{PORT}{path}', new=2)


def port_busy(port):
    """端口有人监听就说明已经起着一个 Movo 了。"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.35)
            return sock.connect_ex(('127.0.0.1', port)) == 0
    except OSError:
        return False


def show_info_dialog(title, message, error=False):
    """Show a simple native dialog that works from the tray thread."""
    if platform.system() == 'Windows':
        try:
            import ctypes
            flags = 0x00000010 if error else 0x00000040  # ICONERROR / ICONINFORMATION
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x00000000 | flags)
            return
        except Exception:
            pass

    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        if error:
            messagebox.showerror(title, message, parent=root)
        else:
            messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except Exception:
        pass


def trust_ssl_certificate():
    """Import the bundled self-signed cert into the current user's Trusted Root store."""
    if platform.system() != 'Windows':
        show_info_dialog('信任 SSL 证书', '当前仅支持在 Windows 上自动导入证书。', error=True)
        return

    pem_path = resource_path('cert.pem')
    if not os.path.exists(pem_path):
        show_info_dialog('信任 SSL 证书', '未找到证书文件 cert.pem。', error=True)
        return

    der_path = None
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding

        with open(pem_path, 'rb') as f:
            cert = x509.load_pem_x509_certificate(f.read())

        fd, der_path = tempfile.mkstemp(suffix='.cer', prefix='movo-cert-')
        os.close(fd)
        with open(der_path, 'wb') as f:
            f.write(cert.public_bytes(Encoding.DER))

        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        result = subprocess.run(
            ['certutil', '-addstore', '-user', 'Root', der_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=creationflags,
        )

        output = ((result.stdout or '') + '\n' + (result.stderr or '')).strip()
        already = 'already in store' in output.lower() or '已经在存储' in output or '已在存储' in output

        if result.returncode == 0 or already:
            show_info_dialog(
                '信任 SSL 证书',
                '已将 Movo 证书导入当前用户的“受信任的根证书颁发机构”。\n\n'
                '请完全退出并重新打开 Chrome / Edge 后再访问本机页面。\n'
                '手机端仍需在手机上自行选择继续访问或信任证书。',
            )
        else:
            show_info_dialog(
                '信任 SSL 证书',
                '导入失败。\n\n' + (output or f'certutil 退出码: {result.returncode}'),
                error=True,
            )
    except Exception as exc:
        show_info_dialog('信任 SSL 证书', f'导入失败：{exc}', error=True)
    finally:
        if der_path and os.path.exists(der_path):
            try:
                os.remove(der_path)
            except OSError:
                pass


def create_tray_image():
    from PIL import Image, ImageDraw

    icon_path = resource_path('static', 'app-icon.png')
    try:
        image = Image.open(icon_path).convert('RGBA')
        return image.resize((64, 64), Image.Resampling.LANCZOS)
    except Exception:
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(16, 38, 26, 255))
        draw.rounded_rectangle((14, 14, 50, 50), radius=8, outline=(89, 227, 145, 255), width=4)
        draw.rectangle((20, 20, 28, 28), fill=(89, 227, 145, 255))
        draw.rectangle((36, 36, 44, 44), fill=(89, 227, 145, 255))
        return image


def start_server():
    socketio.run(
        app,
        host='0.0.0.0',
        port=PORT,
        ssl_context=(resource_path('cert.pem'), resource_path('key.pem')),
        allow_unsafe_werkzeug=True,
    )


def show_startup_dialog():
    """Desktop tip shown when the packaged EXE starts."""
    import tkinter as tk
    from tkinter import font as tkfont

    root = tk.Tk()
    root.title("Movo")
    root.resizable(False, False)
    root.attributes('-topmost', True)

    try:
        root.iconphoto(True, tk.PhotoImage(file=resource_path('static', 'app-icon.png')))
    except Exception:
        pass

    width, height = 420, 210
    x = (root.winfo_screenwidth() - width) // 2
    y = (root.winfo_screenheight() - height) // 3
    root.geometry(f'{width}x{height}+{x}+{y}')
    root.configure(bg='#15151c')

    frame = tk.Frame(root, bg='#15151c', padx=28, pady=24)
    frame.pack(fill='both', expand=True)

    title_font = tkfont.Font(family='Microsoft YaHei UI', size=13, weight='bold')
    body_font = tkfont.Font(family='Microsoft YaHei UI', size=10)

    tk.Label(
        frame,
        text='Movo 已启动',
        font=title_font,
        fg='#ffffff',
        bg='#15151c',
        anchor='w',
    ).pack(fill='x')

    tk.Label(
        frame,
        text='请检查系统托盘，Movo 已在后台运行。\n之后可随时从托盘图标打开触摸板。',
        font=body_font,
        fg='#b0b0b8',
        bg='#15151c',
        justify='left',
        anchor='w',
        pady=(12, 22),
    ).pack(fill='x')

    buttons = tk.Frame(frame, bg='#15151c')
    buttons.pack(fill='x')

    def open_home():
        open_page('/touchpad')
        root.destroy()

    def dismiss():
        root.destroy()

    open_btn = tk.Button(
        buttons,
        text='打开网页',
        command=open_home,
        font=body_font,
        bg='#7b4dff',
        fg='#ffffff',
        activebackground='#6a3de6',
        activeforeground='#ffffff',
        relief='flat',
        padx=16,
        pady=8,
        cursor='hand2',
    )
    open_btn.pack(side='right')

    close_btn = tk.Button(
        buttons,
        text='知道了',
        command=dismiss,
        font=body_font,
        bg='#2a2a35',
        fg='#dddddd',
        activebackground='#3a3a48',
        activeforeground='#ffffff',
        relief='flat',
        padx=16,
        pady=8,
        cursor='hand2',
    )
    close_btn.pack(side='right', padx=(0, 10))

    root.protocol('WM_DELETE_WINDOW', dismiss)
    root.bind('<Escape>', lambda _event: dismiss())
    root.bind('<Return>', lambda _event: open_home())
    root.focus_force()
    root.mainloop()


def run_with_tray(silent=False):
    import pystray
    from pystray import MenuItem as Item

    def on_open_home(icon, item):
        open_page('/touchpad')

    def on_open_setup(icon, item):
        webbrowser.open(welcome_server.setup_url(), new=2)

    def on_trust_cert(icon, item):
        threading.Thread(target=trust_ssl_certificate, daemon=True).start()

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        Item('打开触摸板', on_open_home, default=True),
        Item('设置 / API Key', on_open_setup),
        Item('信任 SSL 证书', on_trust_cert),
        Item('退出', on_quit),
    )
    icon = pystray.Icon('movo', create_tray_image(), 'Movo 已在后台运行', menu)

    # 本地欢迎 / 配置页（127.0.0.1:5889，明文 HTTP，不会有证书警告）
    welcome_server.start()

    server = threading.Thread(target=start_server, daemon=True)
    server.start()

    # Keep tkinter on the main thread; run the tray icon beside it.
    tray_thread = threading.Thread(target=icon.run, daemon=True)
    tray_thread.start()

    # 双击 exe 时把界面交到浏览器；开机自启（--silent）不能弹，否则每次开机都蹦一个网页。
    if not silent and (is_frozen() or os.environ.get('MOVO_SETUP_PAGE') == '1'):
        time.sleep(1.2)   # 等两个服务都完成 bind，页面才打得开
        first = not welcome_server.volc_ready()
        opened = False
        try:
            opened = webbrowser.open(welcome_server.setup_url(first=first), new=2)
        except Exception:
            opened = False
        if not opened:
            # 没有默认浏览器才退回原生小窗
            try:
                show_startup_dialog()
            except Exception:
                pass

    tray_thread.join()


# --- SocketIO 事件绑定 ---

@socketio.on('connect')
def handle_connect():
    os_type = platform.system()
    socketio.emit('os_info', {'os': os_type})
    _diag_write('socket connect')
    # 手机每次连上来先复位按键状态，避免任何残留的“按住”把物理键盘搞乱
    try:
        keyboard_service.release_all()
    except Exception:
        pass
    # 鼠标同理。release_all 里只会松真的按着的键，不会凭空放 UP 出去。
    try:
        mouse_service.release_all('connect')
    except Exception:
        pass


@socketio.on('hb')
def handle_hb(data=None, *args, **kwargs):
    """客户端心跳。有回应就说明连接是真活的 —— 手机靠它识别“假连接”。

    注意：这里绝对不能碰鼠标。心跳每 3 秒一次，一碰就会打断正在进行的拖拽。

    签名必须能吃下客户端发来的 payload：前端是 `emit('hb', {}, cb)`，带一个空对象。
    之前写成 `handle_hb()`，flask_socketio 会按位置参数塞进 `{}` —— 每次心跳都抛
    TypeError，回执永远回不去；前端 `socket.timeout(4000)` 只好判超时，累积 12 秒就
    硬重连一次。表现就是「一直在重连 / 连不上」。这是本轮断联的根因。
    """
    return {'ok': True, 't': time.time()}


@socketio.on('disconnect')
def handle_disconnect():
    """手机断线（切后台、锁屏、App 被杀）时，把还按着的键全部松开。"""
    _diag_write('socket disconnect')
    try:
        voice_service.drop(request.sid)
    except Exception:
        pass
    for release in (lambda: keyboard_service.release_all(),
                    lambda: mouse_service.release_all('disconnect')):
        try:
            release()
        except Exception:
            pass

@socketio.on('load_gp_macros')
def handle_gp_load(data=None):
    data = config_manager.load_gp_macros()
    socketio.emit('gp_macros_loaded', data)

@socketio.on('save_gp_macros')
def handle_gp_save(data):
    config_manager.save_gp_macros(data)
    gamepad_service.update_config(data)

@socketio.on('get_gamepads')
def handle_get_gps(data=None):
    gps = gamepad_service.get_gamepad_list()
    socketio.emit('gamepads_list', gps)

@socketio.on('select_gamepad')
def handle_select_gp(index):
    gamepad_service.selected_index = index
    handle_get_gps() # 刷新状态

# 鼠标事件
@socketio.on('move')
def on_move(data): mouse_service.handle_move(data)

# ---------------------------------------------------------------------------
# 诊断通道：手机端把「按下 / 抬手 / 判定 / 跳转」的时序写进 _diag.log，
# 用来定位“点一下按钮却先冒出一次右键”这类时序问题。
#
# 默认关闭 —— 每次 click / 松键都 open-append-close 一个文件是实打实的磁盘 IO，
# 长期挂机会白写几十万行。要排查时设 MOVO_DIAG=1 再启动服务即可：
#   set MOVO_DIAG=1 && .venv\Scripts\python.exe server.py
# ---------------------------------------------------------------------------
_DIAG_ON = os.environ.get('MOVO_DIAG') == '1'
_DIAG_PATH = os.path.join(app_dir(), '_diag.log')
_DIAG_MAX_BYTES = 2 * 1024 * 1024
_diag_lock = threading.Lock()
_diag_fh = None


def _diag_write(line):
    if not _DIAG_ON:
        return
    global _diag_fh
    try:
        with _diag_lock:
            if _diag_fh is None:
                # 超过 2MB 就轮转一份，避免长期开启把磁盘写满
                if os.path.exists(_DIAG_PATH) and os.path.getsize(_DIAG_PATH) > _DIAG_MAX_BYTES:
                    try:
                        os.replace(_DIAG_PATH, _DIAG_PATH + '.1')
                    except OSError:
                        pass
                _diag_fh = open(_DIAG_PATH, 'a', encoding='utf-8')
            _diag_fh.write(time.strftime('%H:%M:%S') + ' ' + str(line) + '\n')
            _diag_fh.flush()
    except Exception:
        pass


# 鼠标服务也往这份日志里记：谁在什么时候松了哪个键（幽灵右键的取证）
mouse_service.set_logger(_diag_write)

@socketio.on('__diag')
def on_diag(data):
    _diag_write(data)

@socketio.on('click')
def on_click(data):
    _diag_write('CLICK ' + str(data))
    mouse_service.handle_click(data)

@socketio.on('drag_start')
def on_drag_start(data=None): mouse_service.handle_drag_start()

@socketio.on('drag_end')
def on_drag_end(data=None): mouse_service.handle_drag_end()

@socketio.on('mid_down')
def on_mid_down(data=None): mouse_service.handle_mid_down()

@socketio.on('mid_up')
def on_mid_up(data=None): mouse_service.handle_mid_up()

@socketio.on('scroll')
def on_scroll(data): mouse_service.handle_scroll(data)

# 双指捏合缩放：Ctrl + 滚轮
@socketio.on('zoom')
def on_zoom(data=None, *args, **kwargs): mouse_service.handle_zoom(data or {})

# 键盘事件
@socketio.on('type_text')
def on_type(data): keyboard_service.handle_type_text(data)

@socketio.on('key_action')
def on_key(data): keyboard_service.handle_key_action(data)

# 点按一次（退格/回车）：按下即松开，不进入自动重复，不会有键卡住
@socketio.on('tap_key')
def on_tap(data): keyboard_service.handle_tap(data)

@socketio.on('key_combo')
def on_combo(data): keyboard_service.handle_combo(data)

# 键盘页顶栏的功能键：音量 / 静音 / 亮度 / 终端 / 关机
# 返回值带上执行结果，前端拿它做一下 toast 提示（比如"亮度 84%"）
@socketio.on('sys_action')
def on_sys_action(data=None):
    data = data if isinstance(data, dict) else {}
    action = data.get('action')
    url = data.get('url')
    try:
        return system_service.handle_action(action, url=url)
    except Exception as e:
        _diag_write('SYS_ACTION FAIL ' + str(action) + ' ' + str(e))
        return {'ok': False, 'msg': str(e)[:60]}


# --- 语音输入 ---
# 音频走二进制：前端每 100ms 发一包 16kHz 单声道 int16，
# 服务端喂给 sherpa-onnx 的流式识别器，立刻回 partial。
# 这里只做识别，不直接打字 —— 打不打由前端决定（页面上有“自动上屏”开关）。

@socketio.on('voice_status')
def on_voice_status(data=None):
    emit('voice_state', voice_service.status())


@socketio.on('voice_start')
def on_voice_start(data=None):
    if not voice_service.start(request.sid):
        emit('voice_state', voice_service.status())
        return {'ok': False}
    return {'ok': True}


@socketio.on('voice_audio')
def on_voice_audio(pcm):
    if not isinstance(pcm, (bytes, bytearray)):
        return
    res = voice_service.feed(request.sid, bytes(pcm))
    if res['changed'] or res['endpoint']:
        emit('voice_partial', res)


@socketio.on('voice_end')
def on_voice_end(data=None):
    text = voice_service.finish(request.sid)
    emit('voice_final', {'text': text or ''})

if __name__ == '__main__':
    use_tray = os.environ.get('MOVO_NO_TRAY') != '1'
    hide_console = os.environ.get('MOVO_SHOW_CONSOLE') != '1'
    # --silent 给开机自启用：只后台跑，不弹任何界面
    silent = ('--silent' in sys.argv) or os.environ.get('MOVO_SILENT') == '1'

    # 双击 exe 时如果已经跑着一个，就别起第二个实例 —— 直接把界面推到浏览器上。
    if not silent:
        if port_busy(welcome_server.SETUP_PORT):
            webbrowser.open(welcome_server.setup_url(), new=2)
            sys.exit(0)
        if port_busy(PORT):
            # 旧版本实例没有配置页，退回触控板
            open_page('/touchpad')
            sys.exit(0)

    # 启动自检：上一次异常退出可能留下“按住”的鼠标/键盘状态
    for _release in (mouse_service.release_all, keyboard_service.release_all):
        try:
            _release()
        except Exception:
            pass

    if hide_console:
        hide_console_window()

    if use_tray:
        try:
            run_with_tray(silent=silent)
            sys.exit(0)
        except Exception:
            # Fall back to console mode if tray dependencies are unavailable.
            pass

    ips = get_all_ip_addresses()

    print("\n" + "═"*60)
    print("🚀 Remote Pro Server 已启动！")
    print(f"🏠 当前系统: {platform.system()}")
    print("📱 请在浏览器访问以下地址:")
    print(f"🖥️  本机触摸板: https://127.0.0.1:{PORT}/touchpad")
    print(f"⌨️  键盘 / 🎮 手柄: /k  /controller")

    for interface, ip in ips:
        tag = ""
        if any(keyword in interface.lower() for keyword in ["wlan", "wi-fi", "eth", "en0", "en1"]):
            tag = " [推荐]"
        print(f"  ➤  https://{ip}:{PORT}{tag}")

    print("═"*60 + "\n")

    welcome_server.start()
    start_server()
