"""本地欢迎 / 配置服务。

双击 MovoServer.exe 后浏览器打开的就是它，跑在 127.0.0.1 的明文 HTTP 上：
自签证书的 HTTPS 会让浏览器先弹一张"不安全"警告页，第一次用的人直接就被劝退了。
只绑回环地址，局域网里其它设备访问不到，也不会和手机用的 5888 抢端口。

职责只有三件事：
1. 首次运行给出欢迎页 + 功能简介；
2. 让用户填自己的火山引擎「豆包语音识别」API Key（打包的 exe 里不带任何凭证）；
3. 填之前先握手测一下 Key 到底能不能用，别让用户填完发现还是不能用。
"""

import json
import os
import socket
import threading

from flask import Flask, jsonify, render_template, request

from app_paths import app_path, resource_path

SETUP_PORT = int(os.environ.get('MOVO_SETUP_PORT') or 5889)
MAIN_PORT = int(os.environ.get('MOVO_PORT') or 5888)

CONFIG_NAME = 'voice_config.json'

# 新建配置时的默认值，和 voice_volc.DEFAULT_* 保持一致
DEFAULT_VOLC = {
    'api_key': '',
    'app_key': '',
    'access_key': '',
    'resource_id': 'volc.seedasr.sauc.duration',
    'url': 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async',
    'enable_itn': True,
    'enable_punc': True,
    'enable_ddc': True,
    'enable_nonstream': True,
    'hotwords': [],
}

app = Flask(
    __name__,
    template_folder=resource_path('templates'),
    static_folder=resource_path('static'),
)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True


# ---------------------------------------------------------------------------
# 配置读写
# ---------------------------------------------------------------------------

def config_path():
    return app_path(CONFIG_NAME)


def read_config():
    path = config_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def volc_ready(cfg=None):
    """云端语音是否可用：有 api_key，或者 app_key + access_key 都齐。"""
    cfg = cfg if cfg is not None else read_config()
    volc = (cfg or {}).get('volc') or {}
    api_key = str(volc.get('api_key') or '').strip()
    app_key = str(volc.get('app_key') or '').strip()
    access_key = str(volc.get('access_key') or '').strip()
    return bool(api_key or (app_key and access_key))


def save_config(api_key, resource_id=''):
    """只覆盖传入的字段，其它保持原样（用户原来配过热词、url 不会被冲掉）。"""
    cfg = read_config()
    volc = dict(DEFAULT_VOLC)
    volc.update(cfg.get('volc') or {})
    volc['api_key'] = (api_key or '').strip()
    if resource_id:
        volc['resource_id'] = resource_id.strip()
    cfg['provider'] = 'volc'
    cfg['volc'] = volc

    path = config_path()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)   # Windows 上只是尽力而为，NTFS 会忽略
    except OSError:
        pass

    # 改完立刻生效，不用重启服务
    try:
        import voice_service
        voice_service.reload_cloud_config()
    except Exception:
        pass
    return cfg


# ---------------------------------------------------------------------------
# 连通性测试
# ---------------------------------------------------------------------------

def test_api_key(api_key, resource_id=''):
    """只做 WebSocket 握手：火山在握手阶段就校验 X-Api-Key，不必走完整音频协议。

    返回 (ok, message, hint)。hint 是给用户看的下一步动作。
    """
    api_key = (api_key or '').strip()
    if not api_key:
        return False, '还没有填 API Key', ''

    try:
        import websocket
        from voice_volc import VolcConfig
    except Exception as exc:
        return False, f'本机缺少语音组件：{exc}', ''

    cfg = VolcConfig({'api_key': api_key, 'resource_id': resource_id or None})
    try:
        ws = websocket.create_connection(cfg.url, header=cfg.headers(), timeout=8)
    except Exception as exc:
        text = str(exc)
        status = getattr(exc, 'status_code', None) or getattr(exc, 'status', None)
        blob = f'{status} {text}'
        if status == 401 or '401' in blob:
            return False, 'API Key 无效或已被删除', '请到控制台重新复制一次 API Key'
        if status == 403 or '403' in blob or 'not granted' in blob.lower():
            return False, '这个 Key 还没有开通流式语音识别', (
                '在火山控制台开通「流式语音识别大模型」，开通后权限生效可能要几分钟'
            )
        if 'timeout' in text.lower() or 'timed out' in text.lower():
            return False, '连接超时', '检查网络是否通畅（公司网络可能挡了 wss）'
        return False, '连接失败：' + text[:160], ''

    try:
        ws.close()
    except Exception:
        pass
    return True, '连接成功，这个 Key 可以用', ''


# ---------------------------------------------------------------------------
# 局域网地址（给欢迎页显示"手机访问这个地址"）
# ---------------------------------------------------------------------------

def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.3)
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
    except OSError:
        return ''


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@app.after_request
def _no_store(resp):
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/')
def index():
    cfg = read_config()
    volc = cfg.get('volc') or {}
    key = str(volc.get('api_key') or '')
    ip = lan_ip()
    return render_template(
        'welcome.html',
        configured=volc_ready(cfg),
        key_tail=key[-4:] if len(key) > 8 else '',
        resource_id=str(volc.get('resource_id') or DEFAULT_VOLC['resource_id']),
        first=(request.args.get('first') == '1'),
        lan_ip=ip,
        phone_url=f'https://{ip}:{MAIN_PORT}/touchpad' if ip else '',
        local_url=f'https://127.0.0.1:{MAIN_PORT}/touchpad',
    )


@app.route('/api/status')
def api_status():
    cfg = read_config()
    return jsonify({
        'configured': volc_ready(cfg),
        'lan_ip': lan_ip(),
        'main_port': MAIN_PORT,
    })


@app.route('/api/voice-test', methods=['POST'])
def api_voice_test():
    data = request.get_json(silent=True) or {}
    ok, message, hint = test_api_key(
        data.get('api_key') or '', data.get('resource_id') or ''
    )
    return jsonify({'ok': ok, 'message': message, 'hint': hint})


@app.route('/api/voice-config', methods=['POST'])
def api_voice_config():
    data = request.get_json(silent=True) or {}
    api_key = (data.get('api_key') or '').strip()
    if not api_key:
        return jsonify({'ok': False, 'message': '请先填入 API Key'}), 400
    save_config(api_key, data.get('resource_id') or '')
    return jsonify({
        'ok': True,
        'message': '已保存，语音识别现在就能用了',
        'phone_url': f'https://{lan_ip()}:{MAIN_PORT}/touchpad' if lan_ip() else '',
    })


@app.route('/api/voice-config', methods=['DELETE'])
def api_voice_clear():
    """清空 Key（换号或想改回本地识别时用）。"""
    save_config('')
    return jsonify({'ok': True, 'message': '已清空，语音将走本地识别'})


@app.route('/healthz')
def healthz():
    return 'ok'


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------

def run():
    try:
        app.run(
            host='127.0.0.1',
            port=SETUP_PORT,
            threaded=True,
            debug=False,
            use_reloader=False,
        )
    except OSError:
        # 端口被占（已经开着一个 Movo 了），不影响主服务
        pass


def start():
    """后台线程拉起配置服务。返回线程对象。"""
    t = threading.Thread(target=run, daemon=True, name='movo-setup')
    t.start()
    return t


def setup_url(first=False):
    return f'http://127.0.0.1:{SETUP_PORT}/' + ('?first=1' if first else '')
