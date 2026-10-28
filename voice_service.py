"""语音识别服务：火山引擎豆包 2.0（云端）为主，sherpa-onnx SenseVoice（本地）兜底。

链路：浏览器每 100ms 发来一包 16kHz 单声道 PCM(int16)
      → 同时喂给云端会话和本地识别器
      → 云端有字就用云端（带标点、带 ITN、热词表纠正专有名词）
      → 云端出错或没配置时静默回落本地，用户无感

为什么放电脑端（2026-10-28 实测结论）：
  小米 HyperOS 的小爱语音引擎拒绝第三方 App 直接调 RecognitionService
  （19ms 就回 ERROR_INSUFFICIENT_PERMISSIONS），只能走系统浮窗，样式和超时都改不了。
  引擎放电脑后：模型可大可小、样式完全自控，Android 端只是 WebView 跑网页，改网页不用重装 APK。

为什么还要云端（同一天实测对比，同一段中英混说话音）：
  本地 SenseVoice  ：帮我用react写一个to do list组件，用us state管理状态，再加一个taxscript的类型定义。
  云端豆包 2.0     ：帮我用 React 写一个 ToDoList 组件，用 useState 管理状态，再加一个 TypeScript 的类型定义。
  本地模型没有热词/上下文增强，中文语境下的英文专名必错；云端靠热词表 + 二遍识别能订正。
"""
import json
import os
import threading
import time

import numpy as np
import sherpa_onnx

from app_paths import app_dir
from voice_volc import VolcConfig, VolcSession

SAMPLE_RATE = 16000

_lock = threading.Lock()
_recognizer = None
_load_error = ''
_load_ms = 0
_ready = threading.Event()
_sessions = {}
_last_text = {}

# 云端
_cloud_cfg = None
_cloud_sessions = {}
_cloud_box = {}
_cloud_last = {}
_local_kind = ''  # 'sensevoice' | 'streaming' | ''


def model_dir():
    """models/ 下优先选 SenseVoice，其次第一个含 tokens.txt 的目录。"""
    root = os.path.join(app_dir(), 'models')
    if not os.path.isdir(root):
        return None
    dirs = [os.path.join(root, n) for n in sorted(os.listdir(root))]
    dirs = [d for d in dirs if os.path.isfile(os.path.join(d, 'tokens.txt'))]
    for d in dirs:
        if 'sense-voice' in os.path.basename(d).lower():
            return d
    return dirs[0] if dirs else None


def _pick(d, prefix, prefer_int8=True):
    files = [f for f in os.listdir(d) if f.startswith(prefix) and f.endswith('.onnx')]
    if not files:
        return None
    if prefer_int8:
        files.sort(key=lambda f: 0 if 'int8' in f else 1)
    else:
        files.sort(key=lambda f: 0 if 'int8' not in f else 1)
    return os.path.join(d, files[0])


def _load_cloud_config():
    global _cloud_cfg, _load_error
    path = os.path.join(app_dir(), 'voice_config.json')
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        cfg = VolcConfig(raw.get('volc') or {})
        if cfg.ready:
            _cloud_cfg = cfg
    except Exception as exc:
        _load_error = f'voice_config.json 读取失败: {exc}'


def reload_cloud_config():
    """配置页保存后立刻生效，不用重启服务。返回是否成功拿到可用配置。"""
    global _cloud_cfg, _load_error
    _cloud_cfg = None
    _load_error = ''
    _load_cloud_config()
    return _cloud_cfg is not None


def load_async():
    threading.Thread(target=_load, daemon=True, name='voice-load').start()


def _load():
    global _recognizer, _load_error, _load_ms, _local_kind
    _load_cloud_config()
    d = model_dir()
    if not d:
        if _cloud_cfg is None:
            _load_error = '既没有云端配置，也没找到本地模型（models/<目录>/tokens.txt）'
        _ready.set()
        return
    try:
        t0 = time.time()
        name = os.path.basename(d).lower()
        if 'sense-voice' in name:
            # SenseVoice：离线非流式，自带标点 + ITN，中英日韩粤同一模型
            _recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=_pick(d, 'model'),
                tokens=os.path.join(d, 'tokens.txt'),
                num_threads=2,
                language='auto',
                use_itn=True,
                debug=False,
            )
            _vt = 'sensevoice'
        else:
            # 兜底：流式 zipformer（有端点检测，可以边说边出字）
            _recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=os.path.join(d, 'tokens.txt'),
                encoder=_pick(d, 'encoder'),
                decoder=_pick(d, 'decoder', prefer_int8=False),
                joiner=_pick(d, 'joiner'),
                num_threads=2,
                sample_rate=SAMPLE_RATE,
                feature_dim=80,
                decoding_method='greedy_search',
                provider='cpu',
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=2.4,
                rule2_min_trailing_silence=1.2,
                rule3_min_utterance_length=20.0,
            )
            _vt = 'streaming'
        _load_ms = int((time.time() - t0) * 1000)
        _local_kind = _vt
    except Exception as exc:  # 加载失败不能把服务拖死
        _load_error = f'{type(exc).__name__}: {exc}'
    finally:
        _ready.set()


def status():
    cloud_ok = _cloud_cfg is not None
    return {
        'ready': bool(cloud_ok or _recognizer is not None),
        'loading': not _ready.is_set(),
        'error': _load_error,
        'load_ms': _load_ms,
        'model': os.path.basename(model_dir() or ''),
        'engine': 'volc' if cloud_ok else ('local' if _recognizer is not None else 'none'),
        'local_kind': _local_kind,
        'fallback': bool(cloud_ok and _recognizer is not None),
    }


# ---------- 本地识别 ----------

def _local_start(sid):
    if _recognizer is None:
        return False
    with _lock:
        if _local_kind == 'sensevoice':
            # 离线模型：先攒音频，finish 时一次性识别
            _sessions[sid] = []
        else:
            _sessions[sid] = _recognizer.create_stream()
        _last_text[sid] = ''
    return True


def _local_feed(sid, pcm):
    if _recognizer is None:
        return {'text': '', 'endpoint': False, 'changed': False}
    if _local_kind == 'sensevoice':
        with _lock:
            buf = _sessions.get(sid)
            if buf is None:
                return {'text': '', 'endpoint': False, 'changed': False}
            buf.append(pcm)
        return {'text': '', 'endpoint': False, 'changed': False}

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    with _lock:
        stream = _sessions.get(sid)
        if stream is None:
            return {'text': '', 'endpoint': False, 'changed': False}
        stream.accept_waveform(SAMPLE_RATE, samples)
        while _recognizer.is_ready(stream):
            _recognizer.decode_stream(stream)
        text = _recognizer.get_result(stream)
        endpoint = _recognizer.is_endpoint(stream)
        if endpoint:
            _recognizer.reset(stream)
            _last_text[sid] = ''
            changed = True
        else:
            changed = text != _last_text.get(sid, '')
            _last_text[sid] = text
    return {'text': text, 'endpoint': bool(endpoint), 'changed': changed}


def _local_finish(sid):
    if _recognizer is None:
        return ''
    if _local_kind == 'sensevoice':
        with _lock:
            chunks = _sessions.pop(sid, None)
            _last_text.pop(sid, None)
        if not chunks:
            return ''
        pcm = b''.join(chunks)
        if len(pcm) < SAMPLE_RATE:  # 少于 0.5 秒基本是误触
            return ''
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        stream = _recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        _recognizer.decode_stream(stream)
        return (stream.result.text or '').strip()

    with _lock:
        _last_text.pop(sid, None)
        stream = _sessions.pop(sid, None)
        if stream is None:
            return ''
        stream.accept_waveform(SAMPLE_RATE, np.zeros(int(SAMPLE_RATE * 0.3), dtype=np.float32))
        while _recognizer.is_ready(stream):
            _recognizer.decode_stream(stream)
        return _recognizer.get_result(stream)


# ---------- 云端识别 ----------

def _cloud_start(sid):
    if _cloud_cfg is None:
        return False
    box = {'text': '', 'final': '', 'error': ''}
    session = VolcSession(
        _cloud_cfg,
        on_partial=lambda t, b=box: b.__setitem__('text', t),
        on_final=lambda t, b=box: b.__setitem__('final', t),
        on_error=lambda m, b=box: b.__setitem__('error', m),
    )
    session.start()
    with _lock:
        _cloud_box[sid] = box
        _cloud_sessions[sid] = session
        _cloud_last[sid] = ''
    return True


# ---------- 对外接口 ----------

def start(sid):
    cloud = _cloud_start(sid)
    local = _local_start(sid)
    return bool(cloud or local)


def feed(sid, pcm):
    """喂一包音频。云端优先：有新的云端文本就用它，否则用本地（有的话）。"""
    local = _local_feed(sid, pcm)

    cloud_text = None
    with _lock:
        session = _cloud_sessions.get(sid)
        box = _cloud_box.get(sid)
    if session is not None:
        session.feed(pcm)
        if box is not None:
            t = box.get('text') or ''
            if t and t != _cloud_last.get(sid):
                _cloud_last[sid] = t
                cloud_text = t

    if cloud_text is not None:
        return {'text': cloud_text, 'endpoint': False, 'changed': True, 'source': 'volc'}
    return {**local, 'source': 'local' if _recognizer is not None else 'none'}


def finish(sid):
    """收尾：云端等二遍识别的最终结果，拿不到就用本地兜底。"""
    cloud_text = ''
    with _lock:
        session = _cloud_sessions.pop(sid, None)
        box = _cloud_box.pop(sid, None)
        _cloud_last.pop(sid, None)
    if session is not None:
        try:
            cloud_text = (session.finish(20) or (box or {}).get('final') or '').strip()
        except Exception:
            cloud_text = ''
        if not cloud_text and box and box.get('error'):
            _load_error = ''  # 云端失败不写全局错误，本地兜底即可

    local_text = _local_finish(sid)
    return cloud_text or local_text


def drop(sid):
    with _lock:
        _sessions.pop(sid, None)
        _last_text.pop(sid, None)
        session = _cloud_sessions.pop(sid, None)
        _cloud_box.pop(sid, None)
        _cloud_last.pop(sid, None)
    if session is not None:
        try:
            session.abort()
        except Exception:
            pass
