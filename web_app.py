import socket
import psutil
from flask import Flask, redirect, render_template
from flask_socketio import SocketIO
from app_paths import resource_path

app = Flask(
    __name__,
    template_folder=resource_path('templates'),
    static_folder=resource_path('static'),
)
# 允许所有来源跨域，确保手机能连上
socketio = SocketIO(app, cors_allowed_origins="*",
                    # 传输层心跳交给客户端自己的 hb 看门狗去判断（每 3 秒一问，12 秒无回执就重连），
                    # 所以这里用 socket.io 默认的 25/20 就够。以前收紧到 10/10 反而在
                    # 长轮询稍微卡一下时就把连接误杀，制造出一堆“假断线”。
                    ping_interval=25, ping_timeout=20)

# 改 templates/*.html 后不用重启进程（否则每次改样式都要 kill 一次，手机那边就断线了）
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True


@app.after_request
def _no_store_html(resp):
    """页面本身一律不缓存。

    WebView 会缓存 HTML，改完前端后手机上仍跑旧脚本 —— 旧脚本带着坏掉的连接逻辑，
    表现出来就是「一直在重连，怎么都不好」。本地服务，禁止缓存零成本。
    """
    if resp.mimetype == 'text/html':
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    return resp

def get_all_ip_addresses():
    """本机所有对外 IPv4，给启动 banner 打印访问地址用。"""
    ip_list = []
    for interface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                ip_list.append((interface, addr.address))
    return ip_list


@app.route('/')
def index():
    """根路径直接进触摸板。原来的功能主页（dashboard）已按用户要求删掉。"""
    return redirect('/touchpad')


@app.route('/healthz')
def healthz():
    return 'ok'


# ---- 只保留三页：触摸板 / 键盘 / 手柄 ----

@app.route('/touchpad')
def touchpad_page():
    return render_template('index.html')


@app.route('/k')
def keyboard_page():
    return render_template('keyboard.html')


@app.route('/controller')
def controller_page():
    return render_template('controller.html')


@app.route('/voice')
def voice_page():
    """语音输入：手机只采集音频，识别在电脑端（sherpa-onnx 流式模型）完成。"""
    return render_template('voice.html')
