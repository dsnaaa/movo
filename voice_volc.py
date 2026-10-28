"""火山引擎豆包流式语音识别客户端（SAUC v3 二进制 WebSocket 协议）。

协议要点（见 https://www.volcengine.com/docs/6561/1354869）：
  帧 = 4 字节 header + [sequence 4B] + payload size 4B(大端) + payload
  header[0] = (version 0b0001 << 4) | header_size 0b0001
  header[1] = (message_type << 4) | flags
  header[2] = (serialization << 4) | compression
  header[3] = reserved 0

  请求先发 full client request（JSON，gzip），再连续发 audio only（原始 PCM，gzip），
  最后一包 flags 置 0b0010。服务端按包回 full server response（JSON，gzip）。

推荐用 bigmodel_async（双向流式优化版）+ enable_nonstream（二遍识别）：
实时逐字上屏，同时每个分句结束后用非流式模型重识别，最终文本准确率更高。
"""

from __future__ import annotations

import gzip
import json
import queue
import struct
import threading
import time
import uuid

import websocket

URL_STREAM = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
URL_STREAM_ASYNC = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
URL_NOSTREAM = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"

RES_DOUBAO2_HOUR = "volc.seedasr.sauc.duration"
RES_DOUBAO2_CONCURRENT = "volc.seedasr.sauc.concurrent"
RES_DOUBAO1_HOUR = "volc.bigasr.sauc.duration"

MT_FULL_CLIENT = 0b0001
MT_AUDIO_ONLY = 0b0010
MT_FULL_SERVER = 0b1001
MT_ERROR = 0b1111

F_NONE = 0b0000
F_POS_SEQ = 0b0001
F_LAST_NO_SEQ = 0b0010
F_LAST_NEG_SEQ = 0b0011

SER_JSON = 0b0001
SER_RAW = 0b0000
CMP_GZIP = 0b0001
CMP_NONE = 0b0000

# vibecoding 场景预置热词：本地模型会把 us state / we pack / foll back 拆错，
# 云端由热词表直接把这些词抬起来。
DEFAULT_HOTWORDS = [
    "React", "Vue", "Svelte", "Next.js", "Vite", "Webpack", "Rollup", "esbuild",
    "TypeScript", "JavaScript", "Node.js", "npm", "pnpm", "yarn", "bun",
    "useState", "useEffect", "useMemo", "useCallback", "useRef", "useContext",
    "props", "hook", "component", "render", "callback", "async", "await",
    "Promise", "fetch", "axios", "JSON", "API", "SDK", "CLI", "HTTP", "HTTPS",
    "fallback", "null", "undefined", "boolean", "string", "array", "object",
    "Docker", "Kubernetes", "Nginx", "Redis", "PostgreSQL", "MySQL", "MongoDB",
    "Git", "GitHub", "commit", "branch", "merge", "rebase", "pull request",
    "Python", "FastAPI", "Flask", "Django", "Gradle", "Kotlin", "Swift",
    "Android", "iOS", "WebView", "CSS", "HTML", "flex", "grid", "margin",
    "refactor", "debug", "build", "deploy", "lint", "cursor", "prompt",
]


def _header(msg_type: int, flags: int, ser: int, cmp_: int) -> bytes:
    return bytes([
        (0b0001 << 4) | 0b0001,
        (msg_type << 4) | flags,
        (ser << 4) | cmp_,
        0x00,
    ])


def _pack(msg_type: int, flags: int, payload: bytes, ser: int, cmp_: int,
          seq: int | None = None) -> bytes:
    body = gzip.compress(payload) if cmp_ == CMP_GZIP else payload
    out = _header(msg_type, flags, ser, cmp_)
    if seq is not None:
        out += struct.pack(">i", seq)
    return out + struct.pack(">I", len(body)) + body


def _unpack(resp: bytes) -> dict:
    """解析一帧服务端响应，返回 {'type': ..., 'seq':.., 'payload': dict|bytes, 'code':..}"""
    if len(resp) < 4:
        return {"type": -1, "error": "frame too short"}
    msg_type = resp[1] >> 4
    flags = resp[1] & 0x0F
    cmp_ = resp[2] & 0x0F
    off = 4
    code = None
    seq = None

    if msg_type == MT_ERROR:
        if len(resp) >= off + 4:
            code = struct.unpack(">I", resp[off:off + 4])[0]
            off += 4
    elif flags & 0x01:  # 带 sequence（含最后一包的负 sequence）
        if len(resp) >= off + 4:
            seq = struct.unpack(">i", resp[off:off + 4])[0]
            off += 4

    if len(resp) < off + 4:
        return {"type": msg_type, "error": "missing size field", "code": code}
    size = struct.unpack(">I", resp[off:off + 4])[0]
    off += 4
    payload = resp[off:off + size]

    if cmp_ == CMP_GZIP and payload:
        try:
            payload = gzip.decompress(payload)
        except OSError:
            pass

    out = {"type": msg_type, "flags": flags, "seq": seq, "code": code}
    if msg_type == MT_ERROR:
        out["error"] = payload.decode("utf-8", "replace")
        return out

    try:
        out["payload"] = json.loads(payload.decode("utf-8"))
    except Exception:
        out["payload"] = {}
    return out


class VolcConfig:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.api_key = (cfg.get("api_key") or "").strip()
        self.app_key = (cfg.get("app_key") or "").strip()
        self.access_key = (cfg.get("access_key") or "").strip()
        self.resource_id = (cfg.get("resource_id") or RES_DOUBAO2_HOUR).strip()
        self.url = (cfg.get("url") or URL_STREAM_ASYNC).strip()
        self.enable_itn = cfg.get("enable_itn", True)
        self.enable_punc = cfg.get("enable_punc", True)
        self.enable_ddc = cfg.get("enable_ddc", True)
        self.enable_nonstream = cfg.get("enable_nonstream", True)
        hw = cfg.get("hotwords")
        # 空列表也回落到默认热词表，避免配置里留 [] 反而把热词关掉
        self.hotwords = list(hw) if isinstance(hw, list) and hw else list(DEFAULT_HOTWORDS)
        self.uid = cfg.get("uid") or "movo"

    @property
    def ready(self) -> bool:
        return bool(self.api_key or (self.app_key and self.access_key))

    def headers(self) -> list[str]:
        h = [
            "X-Api-Resource-Id: " + self.resource_id,
            "X-Api-Connect-Id: " + str(uuid.uuid4()),
            "X-Api-Request-Id: " + str(uuid.uuid4()),
        ]
        if self.api_key:
            h.append("X-Api-Key: " + self.api_key)
        else:
            h.append("X-Api-App-Key: " + self.app_key)
            h.append("X-Api-Access-Key: " + self.access_key)
        return h


class VolcSession:
    """一次「按住说话」对应一个会话：喂 PCM 进来，回调带出 partial / final。

    on_partial(text)  整句累计文本（可能多次触发）
    on_final(text)    最终文本（会话结束时触发一次）
    on_error(msg)     出错（此时调用方可回落到本地引擎）
    """

    def __init__(self, cfg: VolcConfig, on_partial=None, on_final=None, on_error=None):
        self.cfg = cfg
        self.on_partial = on_partial or (lambda t: None)
        self.on_final = on_final or (lambda t: None)
        self.on_error = on_error or (lambda m: None)

        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.text = ""
        self.error = None
        self.closed = threading.Event()
        self._sent_audio = 0

    def start(self):
        self._thread.start()

    def feed(self, pcm: bytes):
        if not self._stop.is_set():
            self._q.put(pcm)

    def finish(self, timeout: float = 15.0) -> str:
        """标记音频发送完毕，等待最终结果。"""
        self._stop.set()
        self.closed.wait(timeout)
        return self.text

    def abort(self):
        self._stop.set()
        self.closed.set()

    # ---------- 内部 ----------

    def _request_json(self) -> dict:
        req = {
            "model_name": "bigmodel",
            "enable_itn": self.cfg.enable_itn,
            "enable_punc": self.cfg.enable_punc,
            "enable_ddc": self.cfg.enable_ddc,
            "show_utterances": True,
            "result_type": "full",
        }
        if self.cfg.enable_nonstream:
            req["enable_nonstream"] = True
        corpus = {}
        if self.cfg.hotwords:
            corpus["context"] = json.dumps(
                {"hotwords": [{"word": w} for w in self.cfg.hotwords]},
                ensure_ascii=False,
            )
        if corpus:
            req["corpus"] = corpus
        return {
            "user": {"uid": self.cfg.uid},
            "audio": {"format": "pcm", "codec": "raw", "rate": 16000,
                      "bits": 16, "channel": 1},
            "request": req,
        }

    def _run(self):
        ws = None
        try:
            ws = websocket.create_connection(
                self.cfg.url, header=self.cfg.headers(), timeout=10
            )
            ws.settimeout(0.05)
            payload = json.dumps(self._request_json(), ensure_ascii=False).encode()
            # full client request 也占用一个序号（seq=1），音频包必须从 2 开始，
            # 否则服务端报 autoAssignedSequence mismatch。
            ws.send_binary(_pack(MT_FULL_CLIENT, F_POS_SEQ, payload, SER_JSON, CMP_GZIP, seq=1))

            while True:
                try:
                    resp = ws.recv()
                except websocket.WebSocketTimeoutException:
                    break
                except Exception:
                    break
                if isinstance(resp, str):
                    resp = resp.encode()
                r = _unpack(resp)
                if r.get("type") == MT_ERROR:
                    raise RuntimeError(f"volc error {r.get('code')}: {r.get('error')}")
                if r.get("type") == MT_FULL_SERVER:
                    break

            last_sent = False
            seq = 2  # seq=1 已被 full client request 占用
            while not last_sent:
                try:
                    chunk = self._q.get(timeout=0.05)
                except queue.Empty:
                    if self._stop.is_set():
                        ws.send_binary(_pack(MT_AUDIO_ONLY, F_LAST_NEG_SEQ, b"",
                                             SER_RAW, CMP_GZIP, seq=-seq))
                        last_sent = True
                        continue
                    self._drain(ws)
                    continue

                if self._stop.is_set() and self._q.empty():
                    ws.send_binary(_pack(MT_AUDIO_ONLY, F_LAST_NEG_SEQ, chunk,
                                         SER_RAW, CMP_GZIP, seq=-seq))
                    last_sent = True
                else:
                    ws.send_binary(_pack(MT_AUDIO_ONLY, F_POS_SEQ, chunk,
                                         SER_RAW, CMP_GZIP, seq=seq))
                    seq += 1
                self._sent_audio += len(chunk)
                self._drain(ws)

            self._drain_until_final(ws)
        except Exception as e:
            self.error = str(e)
            self.on_error(self.error)
        finally:
            try:
                if ws is not None:
                    ws.close()
            except Exception:
                pass
            self.closed.set()

    def _drain(self, ws):
        while True:
            try:
                resp = ws.recv()
            except websocket.WebSocketTimeoutException:
                return
            except Exception:
                return
            if isinstance(resp, str):
                resp = resp.encode()
            self._handle(resp)

    def _drain_until_final(self, ws):
        deadline = time.time() + 15
        ws.settimeout(0.5)
        while time.time() < deadline:
            try:
                resp = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break
            if isinstance(resp, str):
                resp = resp.encode()
            if self._handle(resp):
                break

    def _handle(self, resp: bytes) -> bool:
        """处理一帧；返回 True 表示这是最终包。"""
        if not resp or len(resp) < 4:
            return True  # 空帧视为服务端已收尾
        r = _unpack(resp)
        if r.get("type") == MT_ERROR:
            self.error = f"volc error {r.get('code')}: {r.get('error')}"
            self.on_error(self.error)
            return True
        if r.get("type") != MT_FULL_SERVER:
            return False

        data = r.get("payload") or {}
        results = data.get("result") or []
        # 文档写的是 list，实际服务端返回的是 dict，两种都兼容
        if isinstance(results, dict):
            results = [results]
        if results:
            txt = (results[0].get("text") or "").strip()
            if txt and txt != self.text:
                self.text = txt
                self.on_partial(txt)

        # 双向流式模式下，服务端用 flags 标最后一包（0b0011 = 带负序号的末包）
        if r.get("flags") in (F_LAST_NO_SEQ, F_LAST_NEG_SEQ):
            if self.text:
                self.on_final(self.text)
            return True
        return False


def transcribe_once(cfg: VolcConfig, pcm: bytes, timeout: float = 20.0) -> str:
    """整段识别（简化用法，内部仍走流式协议）。"""
    box = {}
    s = VolcSession(
        cfg,
        on_partial=lambda t: box.__setitem__("partial", t),
        on_final=lambda t: box.__setitem__("final", t),
        on_error=lambda m: box.__setitem__("error", m),
    )
    s.start()
    step = 3200  # 100ms
    for i in range(0, len(pcm), step):
        s.feed(pcm[i:i + step])
    text = s.finish(timeout)
    if s.error and not text:
        raise RuntimeError(s.error)
    return text
