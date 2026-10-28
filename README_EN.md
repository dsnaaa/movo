<div align="center">

<img src="static/app-icon.png" width="110" alt="Movo">

# Movo

**Turn your phone into a trackpad, keyboard, and voice input device for your PC**

Windows server + Android app · Direct LAN connection · Your data never leaves the local network

[Download](../../releases/latest) · [Quick Start](#-quick-start) · [Troubleshooting](#-troubleshooting)

[简体中文](README.md) · **English**

</div>

---

| Trackpad | Gyro air mouse | Keyboard | Code remote |
|:---:|:---:|:---:|:---:|
| ![Trackpad](img/screenshot-touchpad.png) | ![Gyro](img/screenshot-gyro.png) | ![Keyboard](img/screenshot-keyboard.png) | ![Code](img/screenshot-code.png) |

## ✨ Features

### 🖱 Trackpad

- One-finger move · two-finger scroll · **pinch to zoom** (same as Ctrl + scroll) · three-finger drag
- Right-edge scroll strip: follows your finger, hold the end arrows to keep scrolling; left-handed mode flips it to the left side
- **Gyro air mouse**: lift the phone and point at the screen — the left and right halves act as left and right click
- Quick input bar: typing auto-sends after a pause (pause length configurable), hold backspace for 1 second to clear
- Shortcut row: ESC, volume ±(hold to keep adjusting), and customizable website/app launch keys

### ⌨️ Keyboard

- Full keyboard + F1–F12 + PRTSC / DEL + arrow keys, with press animations and haptics
- Ctrl / Shift / Alt / Win **lock after a 0.6 s hold**, tap once to unlock — no need to keep pressing
- System keys in the top bar: volume / brightness (hardware backlight preferred) / **terminal** / **shutdown** (hold 1 s with a progress bar to prevent accidents)

### 🤖 Code remote

Built as a keyboard for AI coding assistants: send/confirm, stop generation, Tab completion,
arrow navigation, plus one-tap Ctrl+S / Ctrl+Z / toggle line comment. The **full-width mic**
at the bottom records while held; release and the whole sentence lands in the chat box.

### 🎙 Voice input (shared by the trackpad and Code pages)

Hold to talk — text appears on the phone in real time, and the whole utterance is typed at the
PC cursor when you release. Recognition runs **on the PC**: **Volcengine Doubao streaming ASR 2.0**
(first partial in ~0.7 s, built-in programming vocabulary — mixed Chinese/English names like
`useState` / `TypeScript` are almost always right); without an API key or when offline it falls
back to **local SenseVoice** recognition. See [Speech recognition](#-speech-recognition).

### 🔒 Built for reliability

- **Idles the connection after 61 s, wakes instantly on touch**: saves battery, disconnects are always predictable
- Every key press/release is tracked as a pair: disconnects, sleep, and backgrounding reset automatically — **no stuck keys**
- Key state is checked before releasing, so **no phantom right-click menu**; middle/left button watchdogs release as a last resort
- Self-signed HTTPS encryption; traffic stays inside your LAN
- Chinese and English UI + light/dark themes, every setting is remembered

## 🚀 Quick Start

> The phone and the PC must be on the **same LAN** (same router / Wi-Fi).

| Download ([Releases](../../releases/latest)) | Where it goes | Notes |
|---|---|---|
| `MovoServer.exe` | Windows PC | Single portable file, double-click to run, no Python needed |
| `Movo-v2.0.0.apk` | Android 8.0+ phone | Open after installing; the first launch asks for the server address |

1. **PC**: double-click `MovoServer.exe` → the welcome page opens in your browser (optionally enter a speech API key) →
   close the page, the server keeps running in the system tray
2. **Phone**: open Movo → enter the PC address (e.g. `192.168.31.12:5888`) → trust the self-signed certificate on first connect
3. Done — your phone screen is now the trackpad

> - 🔥 If Windows Firewall blocks the first launch, choose "Allow access", or open port 5888 manually
> - 🛡 To control elevated windows (e.g. Task Manager), run the server as administrator
> - 🔁 Double-click the exe again, or use the tray menu "Settings / API Key", to return to the welcome page

Don't want the app? Just open `https://<PC-IP>:5888/touchpad` in your phone browser (the app adds fullscreen, background keep-alive, and native haptics).

<details>
<summary><b>Run from source</b></summary>

```bash
# Windows / macOS / Linux, Python 3.11+
pip install -r requirements.txt
python server.py            # server on 5888 + settings page on 5889 + system tray

# Optional: start on login
install-autostart.bat       # drops a silent launcher into the Startup folder
```

</details>

## 🎙 Speech recognition

Recognition happens **on the PC**; the phone only captures audio (16 kHz PCM over a socket):

| Scenario | Engine | Experience |
|---|---|---|
| API key configured | Volcengine Doubao streaming ASR 2.0 | ~0.7 s to first partial · programming vocabulary · punctuation · accurate mixed CN/EN |
| No key / offline | Local SenseVoice (sherpa-onnx) | Fully offline · English proper nouns often wrong |

- Paste the API key on the welcome page; **Test connection** performs a real handshake (it distinguishes an invalid key / service not activated / network failure), and saving takes effect immediately
- The key is stored locally in `voice_config.json`; **the installer contains no keys**, and usage is billed to your own Volcengine account
- The offline model is not bundled; download it into `models/` when needed (URL in `.gitignore`). A key alone is enough to use voice

## ⚙️ App settings

| Setting | Range |
|---|---|
| Server address | `IP:port` |
| Trackpad sensitivity | 1 ~ 10 |
| Air-mouse sensitivity | 0.1 ~ 5 |
| Auto-send after typing pause | 0.3 ~ 3 s |
| Handedness | Left / right (moves the scroll strip) |
| UI language | 中文 / English |

## 🛠 Build

```bash
# Windows server → dist/MovoServer.exe (PyInstaller one-file)
build_exe.bat

# Android app (requires Android SDK + Gradle 8.9)
cd android && gradlew.bat assembleDebug
```

<details>
<summary><b>Project layout</b></summary>

```
├── server.py            Entry point (Flask + flask-socketio + pynput, port 5888, tray)
├── welcome_server.py    Local settings page 127.0.0.1:5889 (welcome / API key)
├── web_app.py           Routes: /touchpad /k /controller /voice /healthz
├── mouse_service.py     Mouse injection + press bookkeeping + watchdogs
├── keyboard_service.py  Keyboard injection (race-free taps, combos, media keys)
├── system_service.py    Brightness (DDC/CI → gamma fallback) / terminal / shutdown
├── voice_service.py     Voice dispatch (cloud Doubao ↔ local SenseVoice)
├── voice_volc.py        Volcengine Doubao streaming client (SAUC v3 protocol)
├── templates/           Page templates (HTML edits need no restart)
├── static/js/link.js    Connection lifecycle (sleep / wake / heartbeat)
├── static/js/voice.js   Hold-to-talk (shared by trackpad and Code pages)
├── static/js/i18n.js    Chinese/English strings
└── android/             Android WebView shell (native haptics, keep-alive, autostart)
```

</details>

## 🧯 Troubleshooting

| Symptom | Fix |
|---|---|
| Physical keyboard behaves oddly (as if Ctrl is held) | `python release_keys.py` to release stuck keys |
| Mouse clicks stop working | `python release_mouse.py` (usually a stuck middle button) |
| Screen stuck dimmed | `python reset_brightness.py` |
| Phone can't connect | Same subnet → `ping <PC-IP>` → check firewall port 5888 → try `restart-movo.bat` |
| Capture debug logs | Set `MOVO_DIAG=1` and restart; logs go to `_diag.log` (off by default) |

## 🙏 Credits

Started from the open-source project [cornradio/AirMouse](https://github.com/cornradio/AirMouse) and then heavily reworked:
new UI for all three pages with light/dark themes, rewritten connection lifecycle, fixed stuck keys and phantom
right-clicks, integrated voice input, added pinch-to-zoom, rebuilt the Android native shell, and added a
double-click-and-go welcome/setup page. Full history in [CHANGELOG.md](CHANGELOG.md).
