# 本版本改动明细（相对上游 cornradio/AirMouse）

版本标记：`local-20261027`。基于上游 master（commit `0ef9fcf`）修改。
主要改动集中在**触控板页**、**键盘注入安全**、**部署与开机自启**三块，后端路由与协议基本未动。

---

## 1. 触控板页快捷输入条（templates/index.html）

- 顶栏与触控板之间新增常驻输入条 `#qi-bar`：`<input id="qi-text">` + `⌫` + `⏎`，独立 flex 行，
  **不覆盖**触控板；横屏时 `#mouse-page` 改 grid 布局适配。
- **发送即默认**：输入停 600ms 自动 `type_text` 发到电脑并清空；回车立即发；无发送按钮。
- `⌫`：框里有未发字先删自己；框空了给电脑发退格。`pointerdown` 按住每 110ms 连删，
  `preventDefault()` 防输入框失焦/键盘收起。
- `⏎`：框里有字先发送、再给电脑敲回车（搜索确认/聊天发送用）；框空只敲回车。
- 拼音守卫：`compositionstart/end` 期间不自动发送，避免半成品上屏。
- 聚焦输入框自动暂停陀螺仪、blur 恢复；`handleFirstInteraction` 加 `closest('#qi-bar')` 守卫，
  防止点输入框时 click 冒泡又把陀螺仪打开。
- viewport 加 `interactive-widget=resizes-content`，键盘弹出时布局跟随缩放。
- 顶栏麦克风图标改为「唤起/收起键盘」开关，不再跳转 `/v`。

## 2. 触控板右缘滚轮条（templates/index.html）

- `#scroll-edge`：贴 `#pad` 右缘，宽 36px，上下箭头 + 中间细竖条，激活变蓝。
- 上下滑动 = 鼠标滚轮：累积位移每 `SE_STEP=12px` 发一次 `scroll {dy:n}`，方向与手机一致。
- `touchstart/touchmove` 必须 `stopPropagation()` + `{passive:false}`，否则会被触控板
  当成滑动/点击（会在抬手时误发左键）。只发 scroll 不发 move，光标不动。
- 未做惯性滑行（保持每格可控），需要可加衰减滑行。

## 3. 日/夜间主题（templates/index.html）

- 颜色全部收敛为 CSS 变量：`:root` 夜间 / `html[data-theme="light"]` 日间
  （--bg/--nav/--pad/--field/--line/--txt/--accent 等 + `color-scheme`）。
- 切换入口在 ⋮ 菜单第一项；记忆键 `localStorage.movo_theme`；首次跟随系统 `prefers-color-scheme`。
- `<head>` 内联脚本在**首绘前**设置 `data-theme` 并同步 `meta theme-color`，避免闪色。
- 对比度整改：面板分层（夜间 nav `#17171a` / pad `#08080a`，日间 nav `#fff` / pad `#ebebf1`），
  边线提到可见亮度；`.icon-btn` 补 `border: 1px solid transparent`（否则 GYRO 激活态蓝框不显示）。
- 注意：仅触控板页接入；`/k`、`/v`、`/b`、`/controller` 仍是旧配色。新增颜色一律走变量。

## 4. 键盘注入安全（keyboard_service.py / server.py + 前端）

修复了一个会导致**物理键盘错乱**的线程竞态：
`key_action{down}` 会新起自动重复线程，若线程晚于 up 执行，press 会永远没有 release，
单例 Controller 的按键状态卡死（表现为 Shift/Ctrl 被按住、打字变快捷键）。

- 新增 socket 事件 **`tap_key`**（`keyboard_service.handle_tap`）：press → 15ms → release，
  无线程无竞态。短按类操作（⌫、⏎、键盘页单击）全部迁移到它。
- `repeat_key` 全程 `try/finally: keyboard.release(...)`，且 press 前检查 `stop_event`。
- `server.py` 在 socket connect 时调用 `keyboard_service.release_all()`：手机每次连上自动复位按键。
- 新增 **`release_keys.py`**【救急脚本】：一次性 release 所有修饰键/回车/退格/方向键/字母数字。
  键盘错乱时执行 `.venv\Scripts\python.exe release_keys.py`。
- 原则：**任何按下/松开配对，服务端必须保证最终释放，不能依赖手机端按时发 up。**

## 5. 模板热重载（web_app.py）

- `app.config['TEMPLATES_AUTO_RELOAD'] = True` + `app.jinja_env.auto_reload = True`：
  改 `templates/*.html` 后手机刷新即生效，**不用重启进程**（重启会让手机断线）。
  只有改 `.py` 才需要重启。

## 6. 部署与开机自启（新增脚本）

| 文件 | 作用 |
|---|---|
| `setup-new-pc.bat` | 新机一键：建 `.venv` + 装依赖；可带代理参数 `setup-new-pc.bat ip:port` |
| `start-movo.bat` | 前台启动看日志；已有实例会提示而非报 10048 |
| `restart-movo.bat` | kill 5888 占用进程后重启 |
| `start-hidden.vbs` | 静默启动（pythonw，无窗口）；先判端口判重 |
| `install-autostart.bat` | 在启动文件夹生成「薄壳」vbs，**绝对路径**指向本项目；挪目录后需重跑 |
| `remove-autostart.bat` | 卸载自启 + 停服务 |
| `enable-autologon.bat` | 开机自动登录（管理员；密码明文存 Winlogon，仅限信任机器） |
| `disable-autologon.bat` | 恢复登录界面 |
| `regen-cert.py` | 重新生成自签名证书（pyopenssl，10 年，SAN 含 localhost/127.0.0.1） |

- 自启必须用**薄壳**：直接把 `start-hidden.vbs` 复制进启动文件夹是错的——
  它按自身位置解析目录，启动文件夹里没有 `.venv`，开机必报「Python not found」。
- 服务依赖 `cert.pem`/`key.pem`，不会自动生成；git 仓库中不入库，换机后跑 `regen-cert.py`。
- 限制说明：键鼠注入需要交互桌面会话，锁屏/登录界面下无效；
  想开机免输密码用 `enable-autologon.bat`，不存在「不登录就能控制」的实现。

## 7. 幽灵右键 / 幽灵点击（mouse_service.py，2026-10-27 补）

现象：手机**完全不动**，电脑上过一会儿自己冒出一次右键菜单；切页面时更容易触发。

根因不在前端手势判定，而在服务端的"兜底释放"：
`pynput` 的 `Controller.release()` **不检查按键当前状态**，即使键根本没按下也会
向系统发一个 UP 事件（实测 `dist/test_mouse_release.py`）。
而 `release_all()` 会被 connect / disconnect / 启动自检调用 ——
手机每断一次线（切后台、锁屏、跳页面、心跳重连），就凭空放出一个
**孤儿右键 UP**；很多窗口收到 `WM_RBUTTONUP` 就直接弹右键菜单，根本不校验 DOWN。

- 新增 `_is_down(btn)`：用 `GetAsyncKeyState(VK_LBUTTON/RBUTTON/MBUTTON)` 查系统真实状态，
  **没按着就绝不 release**；非 Windows / 查询失败时退回旧行为。
- `_release(btn, reason)` / `release_all(reason)` 全部改为条件式，并记录到 `_diag.log`（`[mouse]` 前缀）。
- `_press` 的前置复位同样条件化（否则 `drag_start` 会先放一个孤儿 LEFTUP）。
- 看门狗超时改走 `_release`（记账里还有该键，必定真松，兜底不受影响）。
- 删掉 `handle_hb` 里 `return` 之后的死代码：心跳每 3 秒一次，**绝不能碰鼠标**，
  否则会打断正在进行的拖拽。
- `release_mouse.py` 急救脚本同样只松真按着的键（否则急救本身会弹出右键菜单）。
- 新增回归测试 `dist/test_mouse_release.py`：无按键时零事件 / 真按住必须松开。
- 顺带：`_diag.log` 现在记录 `socket connect` / `socket disconnect`，便于观察断线频率。

## 8. 快捷控制条（templates/index.html + keyboard_service.py，2026-10-27 补）

按用户手绘 demo（movo-ui-top-aligned.html）调整：

- 输入条下方新增 **quickbar**：`ESC` / `音量 −` / `音量 +` 三格，触控板与陀螺仪两种模式共用。
  统一走 `tap_key`（press→15ms→release，不会卡键）。
  - 音量键**按一下调一格、按住每 130ms 连调**（pointerdown 起 setInterval，松手/滑出即停）；
  - ESC 只发一次（菜单/游戏里连发 ESC 容易出事）。
- 服务端 `keyboard_service` 新增 **MEDIA_KEYS** 表：`volumeup/volumedown/volumemute/playpause/
  next/prev`（含别名）→ pynput `Key.media_*`。pynput 在 Windows 上自动带 EXTENDEDKEY 标志，
  与实体音量键完全等价。已用全局键盘钩子实测：系统真的收到 media_volume_up/down。
- 底部 modebar 改版：`1fr 68px 1fr`、高 76px，中间是 62px 圆形蓝底麦克风大按钮，
  两侧模式按钮改竖排（图标上、文字下），选中态改淡蓝底。
- 滚轮条 44px → 32px；顶栏工具按钮圆角/图标尺寸微调；`.app` 顶部 padding 交给 safe-area；
  矮屏媒体查询同步压缩（quickbar 40px / modebar 66px）。

## 9. 断联根治 + 只保留三页（server.py / web_app.py，2026-10-27 深夜）

### 9.1 心跳回执永远回不去（断联真凶）

`@socketio.on('hb')` 的 handler 写成了 `def handle_hb():`，而前端发的是
`socket.timeout(4000).emit('hb', {}, cb)` —— 带一个空对象 payload。flask_socketio 按
位置参数塞进去，每次心跳都是：

```
TypeError: handle_hb() takes 0 positional arguments but 1 was given
```

异常在不回执的方向上：客户端等满 4 秒判超时 → 累积到 12 秒就 `hardReconnect()`
（`socket.disconnect()` + `connect()`）→ 服务端记一对 `socket disconnect/connect`。
**这就是日志里 12–18 秒一次、成对出现、没完没了的「重连」**，跟网络、跟省电策略都无关。

- `handle_hb(data=None, *args, **kwargs)`，返回 `{'ok': True, 't': ...}`
- 其余无参 handler（`drag_start/drag_end/mid_down/mid_up/load_macros/load_gp_macros/
  get_gamepads`）统一加 `data=None`，杜绝同一类坑
- 服务端 ping 参数 `10/10` → `25/20`（socket.io 默认）：传输层心跳不该比应用层看门狗还急，
  收紧后在长轮询稍卡时会把好连接误杀
- 前端硬重连加 2.5 秒节流、`disconnect()` 后隔 150ms 再 `connect()`（避免和内部 closing
  状态打架）、整页刷新阈值 20s → 30s

### 9.2 页面不缓存

`web_app.py` 加 `after_request`，HTML 一律 `no-store`。WebView 会缓存 HTML，改完前端后
手机上仍跑旧脚本 —— 旧脚本带着坏掉的连接逻辑，就会「怎么重连都不好」。

### 9.3 只保留三页

按用户要求，功能主页和实验页全部删除：

| 路由 | 状态 |
| --- | --- |
| `/` | **302 → `/touchpad`** |
| `/touchpad` 触摸板 | 保留 |
| `/k` 键盘 | 保留 |
| `/controller` 手柄 | 保留 |
| `/healthz` | 保留（探活用） |
| `/connect` `/v` `/test` `/t` `/r` `/b` | **删除（404）** |

删除的模板：`dashboard.html` `connect.html` `voice.html` `buttons.html` `realmouse.html`。
连带清理：触控板 ⋮ 菜单里的「语音输入页」「Macro Deck」两项、键盘页右上角指向 `/v` 的
麦克风按钮、托盘菜单「扫码连接」项、启动横幅里的扫码地址（改为 `/touchpad`）。

## 10. 空闲休眠 + 触碰唤醒（static/js/link.js 新增，2026-10-27 深夜）

用户拍板的连接策略：**不追求永远在线**。闲置 61 秒主动断开；手指一碰屏幕立刻重连。
断连从此是可预期的事，不是随机故障。

### 10.1 为什么这样做

手机切后台/锁屏时 WebView 会把 JS 定时器整个冻结，任何「探测假连接」的方案都会失效，
回来时连接早就是死的。与其挂一根看不见的死连接，不如不看的时候干脆不连——
还顺带省了电。真实断连场景全部收敛到这一条规则里。

### 10.2 实现（static/js/link.js，三页共用）

- **任何交互都续命**：`pointerdown / touchstart / touchmove / keydown / input` 在
  document capture 阶段刷新 `lastAct`；闲置满 `idleMs`（默认 61000，用户指定 1 分 01 秒）
  就 `sleep()`。
- **休眠流程**：先发 `drag_end`/`mid_up`（键盘页先弹起所有锁住的修饰键），留 80ms 让
  消息发出去，再 `socket.disconnect()`。手动断开后 socket.io 不会自动重连，正合需要。
- **触碰即唤醒**：capture 阶段监听按下，`sleeping` 时立刻 `socket.connect()`，
  触摸板页同时 `reset(500)` 静音——「叫醒」的那一下不会变成一次点击。
- **emit 守卫**：给 `socket.emit` 打补丁，未连接时一律丢弃，**不进 socket.io 发送缓冲**。
  否则重连那一刻会把休眠期间攒下的 move 一次性灌给电脑，指针乱飞。
- **状态机**：`ok / sleep / waking / down` 四态回调给页面刷新 UI。
  触摸板页：灰条「已休眠 · 轻触屏幕唤醒」+ 触控板整体压暗到 42%；
  蓝条「正在连接…」；红条「未连接 · 点此刷新」——只有红条允许点击刷新。

### 10.3 自测

- 打开页面静置 85 秒：`connect → (正好 61s) → disconnect`，之后零重连尝试 ✓
- `idleMs=3000` 的测试页：连上 → 3 秒休眠 → 模拟 `pointerdown` → 立刻连回 →
  再 3 秒又休眠，四段全部按预期出现 ✓
- 键盘页 / 手柄页同样接入（各自底部一条状态胶囊），键盘页 `releaseLocks()` 抽成函数，
  休眠、返回共用

## 11. 更名 Movo 随动（2026-10-27 深夜）

产品更名：**Movo / 随动**，标语「随心而动，轻松掌控」。

### 11.1 触摸板主页（templates/index.html）

- 顶栏品牌 `Movo` → `Movo 随动`（随动以小号字距展示，蓝色点缀）
- 触控板水印 `AIR MOUSE` → `MOVO`
- **删除右上角全屏按钮**（用户确认没用）及其 `toggleFullScreen()`——WebView 里
  requestFullscreen 本来也不生效
- 顶栏上移：`.app` 顶部内边距由整行 `env(safe-area-inset-top)` 改为
  `max(6px, inset - 18px)`——图标都在屏幕两侧，中间本来就留空给摄像头挖孔，
  不需要整行下让，图标离顶更近

### 11.2 App 首页重设计（android/.../assets/setup.html）

欢迎/设置页重做成苹果风：渐变圆角 App 图标（指针+随动波纹）、大号 Movo 字标、
「随 动」宽字距副标、标语「随心而动 · 轻松掌控」。连接卡片、灵敏度滑块逻辑不变。

### 11.3 全量改名

- `strings.xml`：App 名 → **随动**，常驻通知「随动 Movo 运行中」，证书弹窗文案
- `themes.xml` / `AndroidManifest.xml`：`Theme.Movo` → `Theme.Movo`
- `server.py`：托盘悬停、通知、tkinter 弹窗标题等可见文案 → 随动 Movo
- 三个网页 `<title>`：`Movo 随动 | 触控板/键盘/手柄`
- **刻意不改**（功能标识符，改了会丢配置/断更新）：包名 `com.dsnaaa.movo`、
  JS 桥 `MovoNative`、localStorage 键 `movo_theme/movo_mode`、
  SharedPreferences 名 `movo`、环境变量 `MOVO_*`、bat/vbs 文件名
- 版本升 versionCode 4 / versionName 1.1.0，重打 APK

## 12. 未改动项

- 端口 5888、HTTPS 自签名、`/` `/touchpad` `/k` `/v` `/b` `/t` `/r` `/controller` `/connect` 路由结构、
  socket 协议事件名（`move` `scroll` `click` `type_text` `key_action` `tap_key` `key_combo`）均保持上游原样，
  前后端可独立回滚。
- `laji/`（旧页备份）、`build/`（pyinstaller 产物）未纳入版本管理。

## 13. 键盘页顶栏功能键（templates/keyboard.html + system_service.py + server.py）

- 键盘页顶部空出的一行改成功能键条：`←返回 | 音量− | 音量+ | 静音 | 亮度− | 亮度+ | 终端 | 关机`，
  图标 + 小字标签，日/夜间主题各一套配色；返回键缩成纯图标胶囊。
- 音量/静音沿用多媒体键（`tap_key` → `Key.media_*`）；亮度/终端/关机走新事件 `sys_action`，
  服务端返回执行结果，前端 toast（如「亮度 84%」「已打开终端」）。
- 音量、亮度按住不放 130ms 连调；**关机必须长按 1.1 秒**（红色进度条填满才触发，松手取消），
  点一下只提示「长按 1 秒关机」。服务端 `shutdown /s /t 3` 再留 3 秒余量。
- 新增 `system_service.py`：
  - 亮度两级实现：先试 DDC/CI 真背光（VCP 0x10），不支持自动退到 `SetDeviceGammaRamp`
    软件压暗（本机小米电视不支持 DDC，实际走 gamma；下限 30% 防全黑）。
  - 服务启动时自检：发现上次被强杀留下的「暗屏残留」（白点 <65530）自动归位 100%；
    退出时 `atexit` 还原曲线；救急脚本 `reset_brightness.py` 一键归位。
  - 终端：Windows Terminal → PowerShell → cmd 依次尝试，`CREATE_NEW_CONSOLE` 独立窗口。
- `link.js` 休眠期间按下的动作会在前端排队（≤4 个），socket 重连成功后补发。
- 键盘页主题脚本支持 `?theme=dark|light` 调试参数（手机端不带，不影响正常逻辑）。

## 14. 组合键自动释放 / 删亮度键 / 触控板媒体键（v1.1.4）

- **组合键不释放（用户实测反馈）**：键盘页长按 Ctrl/Alt/Win 会锁键，之前打完一个键后
  修饰键一直悬在电脑上，之后普通打字全变成快捷键。现在 `sendKey` 检测到有命令修饰键锁着，
  就在 90ms 后把 Ctrl/Alt/Win/Shift 全部弹起（Ctrl+Shift+S 一次松干净）；只锁 Shift 时
  不动（连续打大写/符号）；锁上时另起 10 秒闲置兜底。
- **删除亮度按键**：本机小米电视走 HDMI 不支持 DDC/CI，gamma 压暗实际不可用，
  顶栏改成 `←返回 | 音量− | 音量+ | 静音 | 终端 | 关机`。`system_service` 的亮度逻辑
  保留（启动自检还原暗屏、`reset_brightness.py` 还在用）。
- **触控板快捷栏加媒体键**（3 格 → 4 格）：`ESC | 音量− | 音量+ | 媒体键`。
  - 单击：`sys_action` + `open_url`，电脑端 Chrome 优先、Edge/默认浏览器兜底，
    只放行 http/https（`normalize_url` 拒绝 file:// 之类）。
  - 长按 550ms：弹编辑框改网址，存 `localStorage.movo_media_url`，可恢复默认
    `https://www.bilibili.com`。
  - 新增 `.sheet-mask` 弹层样式 + `.qk-toast` 轻提示，全部走主题变量；`?media=edit`
    是电脑端调试参数。
- 发布：`v1.1.4` Release（Windows 包 `Movo-Server-v1.1.4-win64.zip`，APK 沿用 v1.1.3，
  App 内置页面本轮未改）。

## 15. 设置页跟随主题 + 连接失败回设置页（App v1.2.0）

- **设置页跟随日夜主题**：网页端（触控板 ⋮ 菜单）切换主题时同步写入 App 原生偏好
  `ui_theme`；原生层跳设置页时带 `?t=` 参数，设置页首绘前定主题（URL 参数 >
  原生偏好 > 跟随系统 media query）。三个网页页的主题初始化也加了原生偏好兜底。
- **连接失败不再黑屏**：WebView 主文档加载失败（连不上/超时/拒绝证书）→
  `onReceivedError(isForMainFrame)` 自动回到设置页并弹「连不上电脑」提示，
  地址框保留原值可直接改完重试；「确定」点击后按钮变「连接中…」，
  15 秒没跳走视为超时恢复按钮并提示。
- APK versionCode 8 / versionName 1.2.0，产物 `dist/Movo-v1.2.0-debug.apk`。

## 16. 冷启动快速探测，不同网段不再黑屏（App v1.2.1）

- **问题**：不在同一网段时冷启动直接 `loadUrl(已存地址)`，TCP 要等几十秒才超时，
  期间黑屏无提示（v1.2.0 的 `onReceivedError` 只在报错后才生效，等不到）。
- **修复**：冷启动先在后台线程做 1.5 秒 TCP 探测（Socket connect 超时 1500ms）——
  通了直接进触控板（同网段毫秒级无感）；不通就根本不发起那次会卡死的加载，
  直接回设置页弹「连不上电脑」，改完地址点确定重试。
- APK versionCode 9 / versionName 1.2.1。

---

## 17. 语音输入（电脑端识别，`/voice`）

**背景**：调研 sofatap 语音直写方案时实测——小米 HyperOS 的小爱语音引擎拒绝第三方 App
直接调 `RecognitionService`（19ms 即回 ERROR_INSUFFICIENT_PERMISSIONS，云端鉴权层拒绝），
只能调起系统浮窗（样式/超时全固定）。所以识别引擎放**电脑端**，手机只当无线麦克风。

- **新页面 `/voice`**（templates/voice.html）：按住说话 → 实时字幕（partial 灰色+光标闪烁）→
  说完停顿自动断句 → 整句打到电脑光标处（可用「自动上屏」开关关闭，只看不打）。
  主题跟随全局日夜模式；`?autotest=N` 是调试钩子（就绪后自动录 N 秒，配合 Chrome
  的 `--use-file-for-fake-audio-capture` 可无麦克风跑通全链路）。
- **识别引擎**：sherpa-onnx 流式 zipformer（`sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30`，
  154MB int8，模型放 `models/`，已 gitignore）。实测 RTF 0.10（比实时快 10 倍）、
  首个 partial 约 0.5~0.8s、识别准确；服务启动时后台加载（约 5s），不阻塞其他页面。
- **新服务 `voice_service.py`**：每连接一个 OnlineStream；`feed()` 喂 16kHz int16 PCM、
  返回 `{text, endpoint, changed}`；端点检测 rule1 2.4s / rule2 1.2s / rule3 20s 自动断句；
  `changed` 挡重复包（50→14 条）。
- **socket 协议**：`voice_status` / `voice_start` / `voice_audio`(二进制) / `voice_end`
  → 回 `voice_state` / `voice_partial` / `voice_final`；打字复用现有 `type_text`。
- **音频采集**：网页 `AudioContext({sampleRate:16000})` + ScriptProcessor，
  采样率不符时线性插值重采样；页 pagehide/visibilitychange 自动停录。
- **限制**：Android WebView 里 getUserMedia 需要原生 `onPermissionRequest` 授权，
  当前 APK 未实现 → 手机上暂时会显示「麦克风被拒」，下一步在 APK 里补；
  电脑 Chrome 直接可用（本机 https://127.0.0.1:5888/voice）。
- 依赖新增：sherpa-onnx、numpy（requirments.txt）。

---

## 18. 语音识别切换到云端（火山豆包 2.0），本地作兜底

**背景**：第 17 节用的本地 zipformer 模型英文几乎不可用、没有标点；换成 SenseVoice 后
标点和中文都对了，但**中英混说里的英文专名仍然会散**——同一段音频的实测对比：

| 原文 | 本地 SenseVoice | 云端豆包 2.0 |
|---|---|---|
| 帮我用 React 写一个 todo list 组件，用 useState… | `帮我用react写一个to do list组件，用us state…` | ✅ `帮我用 React 写一个 ToDoList 组件，用 useState…` |
| …data 字段是 null，帮我加个 fallback… | `data字段是n，帮我加个foll back` | ✅ `data 字段是 null 帮我加个 Fallback` |
| 把 npm run build 的输出贴给我…webpack… | `把MPMrun build…是不是we pack…` | ✅ `把 NPM run build…是不是 Webpack…` |
| …for the edge case? | `for DH case.` | ✅ `for the edge case?` |

根因是本地模型没有热词表/上下文增强，中文语境下的英文词会被按中文子词切开。
云端大模型 ASR 正是靠这两项解决，所以引擎换成**火山引擎豆包流式语音识别 2.0**。

**改动**
- **新 `voice_volc.py`**：SAUC v3 二进制 WebSocket 客户端。含双鉴权（新版 `X-Api-Key`
  或旧版 `X-Api-App-Key` + `X-Api-Access-Key`）、gzip 帧、错误帧解析、
  `bigmodel_async` 双向流式 + `enable_nonstream` 二遍识别（流式出字，分句后重识别提升准确率）。
- **内置 80 个 vibecoding 热词**（React/useState/webpack/npm/TypeScript/fallback/Docker…），
  通过 `request.corpus.context` 的 `hotwords` 传递。
- **`voice_service.py` 改双引擎**：同一份 PCM 同时喂云端和本地；云端有字就用云端，
  云端未配置或出错时静默回落本地 SenseVoice，前端无感。`status()` 新增
  `engine` / `fallback` / `local_kind` 字段。
- **本地模型换 SenseVoice**（`sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17`）：
  中英日韩粤同一模型、自带标点和 ITN、RTF 0.03。旧的流式 zipformer 模型已删除。
  注意 `2025-09-09` 那个包**不要用**——README 写明是粤语特化模型（WSYue-ASR），
  英文全大写、日韩乱码、中文丢字。
- **`voice_config.json`**（gitignore）存凭证，模板见 `voice_config.example.json`。
- 状态栏显示「云端就绪 / 本地就绪」，并标注是否启用兜底。

**协议坑（踩过，记下来）**
1. `sequence` 从 `full client request` 就开始计数，它占 seq=1，**第一个音频包必须从 2 开始**，
   否则报 `autoAssignedSequence (N) mismatch sequence in request (M)`。
2. 服务端返回的 `payload.result` 是 **dict** 而不是文档写的 list。
3. 服务开通后鉴权有几分钟传播延迟，刚开通时握手会短暂返回 `403 requested resource not granted`。
4. Resource ID：豆包 2.0 流式小时版是 `volc.seedasr.sauc.duration`（注意 `sauc` 不是 `auc`，
   `auc` 是录音文件识别，两个服务要分别开通）。

**实测**：8.3s 音频，首个 partial 约 0.7s，`finish` 等二遍识别 1.0s 拿到最终文本；全程 15 次文本更新。
依赖新增：websocket-client。

---

## 19. 触控板集成语音输入（v1.3.0，versionCode 10）

**交互**：底部中央的麦克风键从「点击唤起键盘」改成**按住说话**——

- 按住即录（pointer capture，手指滑出圆钮也不会中断录音），手机浮层实时流式出字；
- 松手 → 「识别中…」→「已上屏」，整段一次性打到电脑光标（说话过程中电脑不动，
  避免半句话被云端改写——分句/流式上屏方案试过又撤销，见第 18 节之后的讨论）；
- **轻点**（<320ms 且没识别到字）保留老行为：唤起键盘；
- 说话时浮层盖住触控板（毛玻璃 + 三根跳动音量条），陀螺仪暂停，录音期间
  `link.touch()` 防止 61 秒闲置休眠把连接掐掉；切后台/锁屏自动停录收尾。

**实现**：复用 `/voice` 的整套服务端（`voice_start/audio/end` → `voice_partial/final`），
触控板页只是多了一个采集端 + 浮层 UI，协议零新增。识别结果结尾是英文/代码时
自动补一个空格（`/[A-Za-z0-9.,?!;:)\]}>]$/`），连说两句不粘连。

**APK 改动**：`onPermissionRequest` 之前只在系统权限**已授权**时放行，首次使用必被拒——
现在先 `requestPermissions(RECORD_AUDIO)` 弹系统弹窗，结果回来在
`onRequestPermissionsResult` 里回填 WebView 的挂起请求。首次按住说话会弹一次
「允许 Movo 录音」，同意后不再询问。

**调试钩子**：`/touchpad?vtest=N`——引擎就绪后自动按住 N 秒再松开，且不往电脑打字；
配合 Chrome 的 `--use-file-for-fake-audio-capture` 可无麦克风跑通整条链路
（实测：partial 3.5s 起出字，6s 松手，7.7s「已上屏」，8.4s 浮层收起）。

---

## 20. 打包发布修复（v1.3.0）

- **无控制台 exe 启动即崩**：`server.py` 启动 banner 打印 emoji，而 PyInstaller `--windowed`
  打包后 stdout 走系统 ANSI 编码（中文 Windows 为 GBK），直接抛 `UnicodeEncodeError`
  把进程带走（`https://` 端口根本不监听，双击像没反应）。
  修复：进程启动时把 `sys.stdout/stderr` 统一 `reconfigure(encoding='utf-8', errors='replace')`，
  控制台被重定向到文件时也不会再因为编码问题退出。
- **发布产物进仓库 `download/`**（不再依赖 Release 页，私有库网页直接可下载）：
  - `Movo-v1.3.0.apk`：客户端，v1.3.0 / versionCode 10，含 WebView 麦克风权限申请修复；
  - `Movo-Server-v1.3.0-win64.zip`：服务端单文件 exe + `voice_config.example.json` + `README.txt`。
- **打包验证**：解压到空目录跑 exe → `/healthz` 回 `ok`；socket 冒烟
  `voice_status` 返回 `{ready:true, engine:'volc'}`，说明 `numpy`/`sherpa_onnx`/`websocket-client`
  在 onefile 里都能正常加载，云端豆包链路可用（正弦波音频 `voice_final` 返回空文本，符合预期）。
- 注意：zip **不含**本地 SenseVoice 模型（100MB+），只配云端 key 也能完整用语音。

---

## 21. 麦克风拿不到：原生录音兜底 + 权限提前要（App v1.3.1，versionCode 11）

真机反馈：系统权限明明给了，按住圆钮还是提示「拿不到麦克风权限」。

排查发现两个问题：

- **失败原因被一句话盖住了**：`catch` 里不管什么错都弹「拿不到麦克风权限」，
  `NotAllowedError` / `OverconstrainedError` / `navigator.mediaDevices` 是 undefined
  （非安全上下文、老内核）根本分不出来。现在原样显示错误名，并把
  `isSecureContext`、`mediaDevices` 是否存在、原生桥版本一起上报到 `_diag.log`。
- **约束太细**：`channelCount` / `echoCancellation` / `noiseSuppression` / `autoGainControl`
  一起提，部分 WebView 会直接 `OverconstrainedError`。现在失败后自动退回 `{audio: true}` 再试一次。

两条加固：

1. **权限提前要**：`onCreate` 里 1 秒后就弹一次 `RECORD_AUDIO` 系统窗，
   不再等用户按住圆钮才弹（那次弹窗往往等不到结果——手指早松了，WebView 的请求也可能超时作废）。
2. **原生录音兜底**：WebView 的 `getUserMedia` 彻底拿不到流时，改走 App 内
   `AudioRecord`（16k / 单声道 / PCM16 / `VOICE_RECOGNITION` 源），
   每 100ms 一包 base64 通过 `window.__nativePcm()` 推给页面，
   页面解码成 Int16 塞进同一条 `voice_audio` 通道 —— **服务端一行没改**。
   两条路都失败才报错，且报错里带真实错误名。

`onPermissionRequest` 去掉多余的 `runOnUiThread` 包装：这个回调本来就在主线程，
再 post 一次会让 WebView 认为请求已作废，grant 也就白给了。

---

## 22. 语音浮层样式 + 原生录音改为首选（App v1.3.2，versionCode 12）

真机反馈（网页版 Chrome 一切正常，只有 App 里拿不到麦克风）：

- **原生录音改为首选**：v1.3.1 是「先试 WebView、失败再退原生」，但 WebView 那次失败的
  报错被同步透传给了用户，原生兜底反而没机会证明自己。现在有原生桥就直接用
  `AudioRecord`，不再依赖 WebView 的 `getUserMedia`——自签证书的 https 页面在 WebView
  里被 Chromium 视为不安全来源，powerful feature（麦克风）基本拿不到，这条路不必再试。
- **失败原因码化**：`startMic` 改回 `String`（"ok" / "perm" / "init" / "start:xxx" /
  "new:xxx"），页面 toast 直接显示阶段码，一眼看出卡在哪一层；
  `perm` 时提示「去系统设置里开一下」。
- **语音浮层样式**：文字原来贴着浮层底（`justify-content: flex-end`），手指按在圆钮上
  视线还得往下瞟。改成垂直居中 + 底部留 96px，文字整体上移；字号
  `clamp(19px,5.6vw,25px)` → `clamp(16px,4.3vw,20px)`，行高 1.5，长句不占屏。

---

## 23. 让「页面到底是哪一版」可见（b1028 构建标记）

真机复现：提示还是「拿不到麦克风权限」——**这句话在当前代码里已经不存在了**，
说明手机上跑的是旧页面（多半是服务端用的还是旧 exe：`--add-data templates` 把页面
打进包里，exe 不会热更新，只有直接跑 `python server.py` 才会自动重载模板）。

- 页面加 `V_BUILD = 'b1028-1538'`；按住失败时不再用一闪而过的 toast，而是把原因
  **留在浮层上 3.6 秒**（「原生 perm · 网页 NotAllowedError · b1028-1538」），可以截图。
- 原生录音启动后 1.2 秒内一包 PCM 都没收到 → 浮层显示「没收到声音数据 b1028-1538」，
  区分「录音没启动」和「启动了但数据没上来」。
- 重新打包 `Movo-Server-v1.3.2-win64.zip`（内含新页面），README 里写明服务端和
  App 要成对更新。

---

## 24. 新版视觉（用户设计稿）+ 透明系统栏 / 全屏开关（App v1.4.1，versionCode 14）

按用户自制的触控板页设计稿（Movo_底栏光效_修复版）整体换肤，并落实「系统栏要回来」：

- **触控板页对齐设计稿**（与 build/design_v2.html 逐字节 diff 校验）：石墨底 + 琥珀
  accent 双主题配色、手写连笔 Movo 字标（内联 SVG）、底栏去掉卡片改成图标+文字、
  中央 66px 独立大话筒、触摸板渐变 + 微点阵 + **跟手光效层**（触摸时光晕跟随，
  轻点有涟漪环，纯视觉不拦事件）。
- **/k、/controller 配色同步**：两页主题变量整体换成新色板（夜间琥珀 / 日间浅蓝），
  键盘页底色与按下态高亮、手柄页卡片与描边一并统一。
- **透明系统栏（不再有黑色条）**：内容延伸到状态栏 / 导航栏下面，系统栏透明，
  图标浮在页面底色上；日间自动用深色图标（读 ui_theme 偏好，网页切主题实时重涂）。
  页面顶部避让改由 `env(safe-area-inset-*)` 完成（App 在 html 上注入
  `data-sysbars="on|off"` 供顶栏公式切换），/k 四边避让、/controller 与 setup 原本就有。
- **设置页新增「显示模式」**：显示系统栏（默认）/ 全屏沉浸，切换立即生效
  （原生 `applyFullscreen()` 桥），不用退出重进。
- 踩坑：onCreate 里 applySystemBars 走到 pushSysBarsToPage 时 webView 尚未创建，
  lateinit 直接 UninitializedPropertyAccessException 闪退（v1.4.0 首次安装启动即崩）。
  已加 isInitialized 守卫。

---

## 25. 设置页统一主题 + Web Coding 图标 + 系统栏避让改原生注入（App v1.4.2，versionCode 15）

- **三点按钮直进设置**：触控板右上角 ⋮ 不再弹菜单，直接打开设置页（浏览器里退化为切主题）。
  日间 / 夜间统一收进设置页的「主题」开关（写 ui_theme 原生偏好，本页即时换肤，
  系统栏图标明暗由原生重涂），下拉菜单及配套 CSS/JS 全部删除。
- **Web Coding 图标**：顶栏原「手柄映射」的手柄图标换成 `</>` 代码图标（该按钮去 /controller，
  页面标题本来就是「Movo 随动 | Code」）。
- **主题读取顺序修正**：三页首绘改为 原生偏好 > localStorage > 跟随系统（原来 localStorage 优先，
  App 里设置页改了主题会被旧 localStorage 盖掉）；读到后回写 localStorage 保持一致。
- **系统栏避让改原生注入（关键修复）**：键盘页在 App 里完全不避让状态栏——
  WebView 的 env(safe-area-inset-\*) 拿不到状态栏高度，键盘页因此整块顶到状态栏底下。
  现在原生用 OnApplyWindowInsetsListener 拿真实像素，按 dp 注入
  `--satop/--sabottom/--saleft/--saright` CSS 变量（页面加载完 + insets 变化时都推）；
  全部页面的避让公式改为 `var(--saX, env(...))`：App 里用原生值，浏览器里 env 兜底。

---

## 26. 键盘页固定全屏（App v1.4.3，versionCode 16）

- 键盘页 /k 不再纠结状态栏避让：**一进 /k 原生直接隐藏系统栏**（状态栏 + 手势条），
  返回触控板自动恢复——和设置里的「显示模式」互不干扰，其它页面照旧。
  实现：WebViewClient 的 onPageStarted / onPageFinished 里按 URL 路径（/k）切换
  `pageFullscreen` 标记并重跑 applySystemBars()；onResume 再收一遍（防止后台切回时系统栏被放出）。
- 键盘页在 App 里因此永远是完整一屏按键，浏览器里不受影响。
- 顺带清掉 pushBarsToPage 里调试用的 document.title 注入，debug 构建保留 WebView 远程调试开关。

---

## 27. 三页顶部控件对齐（App v1.4.4，versionCode 17）

- 问题：触控板 / coding / 设置三页首行控件的顶端像素不一致，切换页面时顶部会跳动。
  真机实测（satop=43px）：触控板 48px、coding 44px、设置 61px。
- 原因：三页各写各的公式——触控板 `satop + 4`、coding `max(10px, satop)`（少了 4px）、
  设置 `10px + satop` 且 header 又自带 8px 上内边距（多出 18px）。
- 统一基准 `max(6px, calc(var(--satop, env(safe-area-inset-top, 0px)) + 4px))`：
  显示系统栏时 = 状态栏 + 4px，全屏（satop=0）与浏览器里保底 6px。
  coding 页 body 与设置页 body[data-mode=settings] 都改成该公式，
  设置页 header 的 padding-top 归零（logo 顶从 61 → 47）。
- 复测三页首行：47 / 48 / 47，肉眼对齐（±1px 来自元素自身居中）。
- 工具：build/measure_top.py（headless Chrome 量三页坐标）、
  build/shot_align.py（三页顶部拼图 + 47px 红线对比图 build/shots/align_top.png）。
- setup.html 打在 APK assets 里，此改动必须重打包：v1.4.4 已装机并归档 dist/download。

---

## 28. 设置页换琥珀色板 + 顶栏改紧凑行；修地址保存失效（App v1.4.5~1.4.6）

- **设置页配色跟上新设计**：原来还是旧黑底蓝 UI，与 coding 页的石墨+琥珀完全脱节。
  现在夜间 = 石墨底 #1b2028 + 琥珀 accent #f1a544（选中态文字用深色 --on-ink），
  日间 = 浅底 + 蓝 #257ee9；logo 渐变、toast、分段控件全部走变量。
- **设置页头部改成紧凑顶栏**（← 返回 + 设置 + 品牌小字，行高与 coding 页一致），
  去掉居中 56px 大 logo——三页首行视觉结构统一。
- **真机实测对齐**：触控板 47 / coding 47.8 / 设置 47（加载瞬间会看到 42 左右的过渡态，
  稳定后一致）。真机测量脚本 build/adb_measure.py（CDP，自动 adb 重连）。
- **修 saveUrl 桥缺失（老 bug）**：setup 页一直调用 N.saveUrl()，而桥方法在重构后叫
  setUrl——地址从未真正保存过，App 数据一清就回配置页且确定后不记忆。
  桥里补 saveUrl 兼容别名（v1.4.6）。装机后验证重启直接进触控板。
- v1.4.5（设置页换肤）与 v1.4.6（桥修复）均已装机并归档 dist/download。

---

## 29. 修「切换页面时整页往下抖一下」：系统栏尺寸改 document-start 注入（App v1.4.7）

- 现象：从 coding 页、设置页返回主页时，主页内容会先低一点再弹上去（向下抖动）。
- 根因：系统栏的 CSS 变量（--satop 等）和 data-sysbars 只在 onPageFinished /
  insets 回调里由 evaluateJavascript 注入。每次返回主页都是一次全新的页面加载，
  首帧还没有这些变量 → 页面先按「没有状态栏」排版（padding-top 6px），
  注入到了才跳到 47px，位移 41px。
- 修法：用 androidx.webkit 的 `WebViewCompat.addDocumentStartJavaScript`，
  在文档开始解析、任何页面脚本和首次绘制之前，把 --satop/--sabottom/--saleft/--saright
  与 data-sysbars 直接写进 html 元素；insets 变化 / 显示模式切换 / 进出键盘页时
  重新注册（值没变则跳过）。首次注册在 setContentView 之后（此时 lastBars 还没来，
  先用系统资源 status_bar_height / navigation_bar_height 估算，随后被真实值替换）。
- 实测（CDP 在 document-start 挂 rAF 轮询，记录首帧坐标）：触控板、coding、设置页
  首帧均为 47px、--satop 已是 43px——不再有落地再跳的过程。
- 工具：build/first_frame_check.py（首帧位置回归测试）。

---

## 30. UI 统一三连：键盘页返回胶囊、发送键箭头、悬浮滚轮（服务端模板）

- **键盘页返回**：34×32 的纯图标小方钮改成和 coding / 设置页同款的「‹ 返回」胶囊
  （34px 高、padding 0 13px 0 9px、13px 字号），功能键条同高 34px 整行齐平。
- **首页发送键**：输入条右侧回车键 ↵ 折角图标换成向上箭头 ↑（title/aria 同步改「发送」）。
- **滚轮融合**：触控板不再给滚轮留独立列——`#pad` 占满整块，滚轮变成浮在触控板上层的
  半透明磨砂胶囊（absolute，右侧 10px，宽 36px，竖向居中 64% 高，毛玻璃 blur）。
  平时 55% 透明度浅浅一层，按住/拖动时亮起（琥珀 accent 光晕）。上/下箭头沿用
  「轻点滚一格、长按连续滚」，条身跟手滚动不变。左撇子模式（hand_mode）胶囊换到左侧。
  新增 --float-* 变量组（日/夜两套），陀螺仪视图的滚轮仍是独立卡片不受影响。
- 全部改动在 templates/（服务端页面），TEMPLATES_AUTO_RELOAD + no-store，手机刷新即生效，
  无需重打包 APK、无需重启服务。预览：build/shot_ui.py（headless Chrome 截触控板/发送键/键盘页）。

---

## 31. 返回语义改「再按一次返回桌面」+ 悬浮滚轮改「只留滑块」（App v1.4.8）

- **返回键不再层层倒退**：原来每点一次模块（键盘 / coding / 设置）都是一次网页跳转，
  历史越攒越长，按返回要退好几次才出得去。现在：
  - 系统返回键：第一次提示「再按一次返回桌面」，2 秒内再按 → moveTaskToBack(true)
    回手机桌面（App 留在后台，socket 不断，再进来还是原页面）；
  - 页面间跳转全部改 location.replace()，不再往 WebView 历史里叠加；
  - 页面内的「‹ 返回」按钮仍是直接回触控板主页（setup.html 的 backHome 走原生 goTouchpad）。
- **悬浮滚轮换「方案 B 只留滑块」**（用户在 5 方案对比图里选定）：
  平时胶囊底 / 描边 / 上下箭头全部隐形，只露一条 6px 细滑块（--float-thumb-idle，
  日/夜两套颜色），像手机右缘的滚动指示器；手指按上去才浮出磨砂底 + 琥珀描边，
  箭头同时淡入（轻点滚一格、长按连滚不变）。滚轮样式在 templates/，手机刷新即生效。
- 工具：build/wheel_options.py（5 方案 × 常态/按住 对比图，用户据此选择）。
- v1.4.8（versionCode 21）已装机并归档 dist/download；滚轮样式无需重打包。

---

## 32. 白条撑满滚轮 + 返回键按层级退（App v1.4.9）

- **滚轮白条撑满整条控件**：去掉上下箭头按钮，滑块改成从顶到底的 8px 细条。
  交互合三为一（bindWheel）：按在白条上半 = 向上翻、按在下半 = 向下翻；
  按住不动 = 连续滚（60ms 一格）；手指移动超过 10px 自动切成跟手拖动（每 12px 一格）。
  按住时白条变琥珀色（--float-thumb-on）、磨砂底浮出。陀螺仪页滚轮保持原样。
- **返回键按页面层级退一层**（替换上一版的「双击回桌面」）：
  触控板主页按返回 = 直接回手机桌面（moveTaskToBack，不用按两次）；
  键盘页 / coding 页 / 设置页按返回 = 一律回触控板主页（不退出、不层层倒退）。
  判定：Uri.parse(webView.url).path 是否为 /touchpad；回主页时 https 页面用
  location.replace('/touchpad')，本机 setup.html 用 loadSaved()；
  首次欢迎页（地址未配置）按返回直接退桌面。
- v1.4.9（versionCode 22）已装机并归档；滚轮样式在 templates/，刷新即生效。

---

## 33. 滚轮微调：白条调淡、两端箭头常驻（服务端模板）

- 用户反馈白条颜色太深：常态透明度 .28/.30 → .13/.15（夜/日），按住高亮也稍降。
- 上/下箭头加回来（用户滑动时要靠它们辨认方向）：改为纯视觉提示，叠在白条两端，
  pointer-events:none，事件仍由滚轮整体统一处理（按上/下半＝对应方向连滚，逻辑不变）。
  箭头带 drop-shadow 光晕（--float-arrow-halo）避免和白条糊在一起，按住时变主题色。
- 全在 templates/，手机刷新即生效，无需重打包 APK。

---

## 34. 滚轮回到三段式版式：箭头各占一行、竖条加长且更淡（服务端模板）

- 用户反馈上一轮「箭头叠压在竖条上」的画法丑：恢复最初的版式——
  上箭头 / 中间竖条 / 下箭头三段竖排，箭头各占一行（22px），竖条夹在中间撑满轨道。
- 竖条透明度再降：夜 .09 / 日 .10，常态只是浅浅一条；按住仍变主题色（琥珀/蓝）+ 磨砂底。
- 删掉叠压方案专用的 drop-shadow 光晕变量（--float-arrow-halo）。
- 纯模板改动，手机刷新即生效。

---

## 35. 底栏触摸板 / 陀螺仪图标换新（服务端模板）

- 出 6+6 套候选渲染对比图（build/icon_options.html → build/shots/icon_options.png），用户选定：
  - **触摸板 = B「触控板+分界线」**：圆角方框 + 底部按键分界线 + 手指圆点（替代方框+指针）；
  - **陀螺仪 = D「机械陀螺」**：正交双椭圆 + 中心点（替代 42° 斜置的原子轨道，更对称）。
- 候选工具沉淀：build/icon_options.html 可继续加变体重渲染。
- 纯模板改动，手机刷新即生效。

---

## 36. 退格键变红 + 长按清空输入框（服务端模板）

- 输入条退格键换成红色（--rec 色系：红描边 + 淡红底 + 红图标），和右侧琥珀色发送键形成
  「删除 / 发送」的红黄对仗。
- 新增长按功能：**按住 460ms 清空输入框里的全部文字**——清空时输入框红框闪一下 +
  一次 CONFIRM 震动；清空会同时取消「停顿自动发送」的排期，字不会漏发到电脑。
  框里本来就没字时，长按退化为原来的「按住连删电脑上的字」，不白按。
- 短按行为不变（删一个字）；重写了退格的事件状态机（hold 计时 + done 标记，
  防 pointerleave/pointerup 双触发）。headless 实测：短按 ABCDE→ABCD、
  0.3s 未触发、0.65s 清空且 cleared 反馈亮起、松手无二次删除。
- 纯模板改动，手机刷新即生效。

---

## 37. 退格键改「实心淡红 + 白图标」、长按阈值改 1 秒（服务端模板）

- 按用户反馈重画：不是"淡红底上的红图标"，而是**整块淡红实心底 + 淡红描边 + 白色图标**，
  和右侧发送键同一套逻辑（实心底 + 白图形）。红比纯红浅一档（夜 #d95a52 / 日 #e0605a，
  描边再亮一档），新增 --del-bg/--del-line/--del-weak 变量。
- 长按清空阈值 460ms → **1000ms**（0.75s 实测不触发、1.2s 触发）。
- 纯模板改动，手机刷新即生效。

---

## 38. 键盘页退格键变红、设置页整理 + 全线中英文切换（App v1.5.0，versionCode 23）

- **键盘页 BackSpace 换红色**：实心淡红底 + 淡红描边 + 白字（--kb-del/--kb-del-line，
  夜 #d95a52 / 日 #e0605a），与触控板输入条那枚退格键同一套逻辑。
- **设置页**：①「操作手」左右手换位——左手在左、右手在右；②删掉没用的「返回触控板」
  按钮（与「确定」同逻辑）；③新增「语言 / Language」分段控件（中文 / English），
  写原生偏好 ui_lang，本页立即换文案、其它页面下次加载自动跟随。
- **全线中英文**：新增 static/js/i18n.js 词表与应用器（data-i18n / data-i18n-ph /
  data-i18n-title / data-i18n-aria 四种挂载 + MovoLang.t() 动态取词），
  触控板 / 键盘 / Code / 设置四页全部接入；语言来源 ?lang= → 原生偏好 ui_lang →
  localStorage.movo_lang → 默认中文。浏览器调试可加 ?lang=en。词表同步复制到
  APK assets（setup.html 是 file:// 页）。
- 长按退格清空的交互逻辑用户暂缓，本版未改动（阈值 1 秒）。

---

## 39. 纠偏：红色退格在 Code 页而非键盘页；Code 页移除「命令宏」

- 上轮理解错了：用户说的「删除键 Backspace 变红」指 **Code 遥控器页**，不是键盘页。
  - 键盘页 BackSpace 恢复原样（k-wide），移除 .k-del 样式与 --kb-del 变量；
  - Code 页「⌫ 退格」键变红（.key.key-del：--del-bg/--del-line，夜 #d95a52 / 日 #e0605a，
    整块淡红底 + 淡红描边 + 白字，含按下态）。
- **Code 页整块移除「命令宏」**：底部宏按钮区、宏编辑弹层、宏 JS（localStorage 读写/
  长按编辑/发送回车）与宏样式全部删除。git 历史可随时找回。
- 纯服务端模板改动，手机刷新即生效，无需重装 APK。

---

## 40. 语音输入抽成共用模块 + Code 页加「按住说话」（键盘页退格恢复红色）

- **键盘页 BackSpace 恢复红色**（上一轮按错误页面撤掉了）：k-del 样式与 --kb-del 变量原样加回。
- **Code 页「⌫ 退格」恢复普通色**（红色只留给收音中的话筒按钮）；命令宏保持已删除状态。
- **语音输入抽成 static/js/voice.js（MovoVoice.attach）**：触控板页 450 行内联语音逻辑
  原样搬进共用模块（原生 AudioRecord 兜底 / getUserMedia 回退 / 100ms 分包 /
  松手整段 type_text 上屏 / ?vtest 调试钩子全部保留），页面只接自己的动作——
  触控板：onStart 暂停陀螺仪、onTap 轻点唤起键盘、onTyped 闪输入框；
  Code 页：无输入框，不做轻点唤起，松手直接上屏。
- **Code 页底部新增「语音输入」区**（原命令宏的位置）：全宽琥珀色大话筒按钮 +
  底部升起浮层实时显示识别文字；按住收音时按钮变红呼吸（--rec 变量）。
  i18n 新增 cp.grp.voice / cp.voice.hold 两键，assets 已同步。
- headless 双页回归：/controller 与 /touchpad 按住→浮层→松手→「已上屏」全链路通过，
  零 JS 异常。纯模板/静态文件改动，手机刷新即生效，无需重装 APK。

---

## 41. Code 页语音浮窗不再遮挡内容（reserve 占位模式）

- voice.js 新增 `reserve: true` 选项：浮层出现时按其当前高度给 body 垫等高下内边距，
  并把页面滚到底——浮层正好落在新垫出来的空白上，编辑/窗口与文件等按钮一个都不压；
  文字变长浮层变高时用 ResizeObserver 跟着重算；收层时还原原 padding。
- 坑：`scrollTo({behavior:'smooth'})` 在 headless/WebView 里会被打断滚不动，
  改成即时 `scrollTo(0, scrollHeight)` 才稳定（scrollY 0 → 148 实测到位）。
- 触控板页不启用（浮层盖住触控板本来就是设计）。headless 矮视口实测零重叠、
  收层后 padding 还原。纯模板/静态改动，刷新即生效。

---

## 42. 纠偏：Code 页语音浮窗改为「挂在话筒按钮上方」（撤销占位方案）

- 上一轮理解错了：用户要的是**浮窗本身往上挂**，不是把页面滚到底/垫空白。
  已整块撤销 reserve 占位逻辑（body padding、scrollTo、ResizeObserver 重垫全删）。
- voice.js 新增 `aboveBtn: true`：浮层出现时按话筒按钮的实时位置计算 bottom
  （按钮上边缘再往上 10px，clamp 不顶出屏幕），页面完全不动，盖住下面内容是预期行为；
  文字变长时重新摆位（schedulePlace），收层后下次出现重算。窗口 resize 跟随。
- 触控板页不用 aboveBtn，浮层仍贴底，不受影响。headless 实测：scrollY 保持 0、
  浮层底边贴按钮上沿、无 JS 异常。

---

## 43. 触控板双指捏合缩放（Ctrl + 滚轮）

- **手势**：双指间距变化超过 30px 判为捏合，本手势内锁定为缩放（不再滚动）；
  之后每变 26px 缩一档，两指张开 = 放大、捏合 = 缩小；轻震反馈同滚动。
  间距不变的双指平移仍然是原来的滚动（改用两指中点算纵向位移，比只看第一根手指稳）。
- **链路**：touchpad.js → `zoom {dir, steps}` → server.py `on_zoom` →
  `mouse_service.handle_zoom`：Ctrl(或 macOS Cmd) 按下 → 滚轮 → 抬起，
  等价于应用里的 Ctrl+滚。严格保证「先按后滚再抬」，应用靠 VK_CONTROL 状态判断，
  顺序错了就没反应；`pressed()` 上下文保证异常也会抬起，不会把 Ctrl 卡在按下。
- steps 夹在 1~6，防止误触一次放大过头。默认开启，无设置项。
- 单测 `build/test_zoom.py`（monkeypatch，不动桌面）验证方向/档数/顺序；
  headless 模拟两指张开、捏合、双指平移、单指滑动四种情况，无 JS 异常。
- moment：touchpad.js 引用加版本号 v=20261028c，防 WebView 用旧缓存。
  改的是 .py（mouse_service/server），需重启服务；APK 不用重装。

## 44. 项目瘦身与性能清理（2026-10-28）

一次性做了三件事：删冗余、去死代码、去掉几处白白的开销。功能行为不变。

**删掉的冗余文件**（工作区 1.2G → 约 640M）

| 类别 | 内容 | 体量 |
| --- | --- | --- |
| 临时目录 | `_tmp_chrome_*`（headless 截图用的 Chrome profile，28 个） | 225M |
| 构建中间产物 | `build/pyinstaller/`、`__pycache__/` | 110M |
| 历史发布包 | `download/`、`dist/` 里 1.0~1.4 的旧 apk / zip | 300M |
| 死静态资源 | `static/buttons/*`（/buttons 页已删）、`controller/controller.js|css`
（Code 页不用手柄）、`sortablejs.js`、`macro.png` | — |
| 一次性脚本 | `_demo.css`、`_shot_pad.py`、`_shots/`、`build/*.html` 快照 | — |
| 过期文件 | `Movoserver.bat`（旧入口）、`requirments.txt`（拼错且缺依赖）、
`Movo.spec`（旧 spec）、`macro_configs.json`、`test.txt`、`deps_ok.txt` | — |

`dist/` 只留 `Movo-v1.5.0.apk` + `MovoServer.exe` + `README.txt`；测试脚本移到 `build/`。
`.gitignore` 去重整理，补上 `download/` 和 `_diag.log*`。

**去死代码**

- 宏功能：Code 页的宏早就删了，但 `load_macros` / `save_macros` 两个 socket 事件、
  `config_manager.load_macros/save_macros` 和 `macro_configs.json` 还留着 —— 全删。
  前端（含此前残留的 `buttons.js`）已无任何调用点。
- `web_app.py`：`get_connection_targets` / `get_outbound_ip` / `get_interface_*` 等 6 个函数
  （~90 行）只服务于已下线的 connect 页 —— 删。`platform`、`request` 两个 import 顺手去掉。

**性能 / 健壮性**

- **触控板每帧多等 10ms**：`handle_move` 每次都调 `wake_up_cursor()`，里面有两次
  `mouse_event` + `time.sleep(0.01)`。改为 30 秒节流 —— 唤醒系统/显示器一次就够，
  不该每个 move 都付这 10ms（这段延迟直接叠在跟手感上）。
- **每秒空广播**：`status_thread` 原来每秒向所有连接 emit `gp_status`。改成只在状态变化时推，
  外加 30 秒兜底补发（给中途打开页面的客户端补状态）。
- **诊断日志默认关**：`_diag_write` 之前每次 click / 松键都 `open-append-close` 一次文件，
  长期挂机会白写几十万行。现在默认不写，排查时设 `MOVO_DIAG=1` 才开；文件句柄常开，
  超过 2MB 自动轮转成 `_diag.log.1`。
- **handler 缺字段不再崩**：`key_action` / `type_text` / `key_combo` 改用 `.get` 取字段。
  （handler 抛异常 → 回执回不去 → 客户端判假连接反复重连，这个坑踩过。）
- **依赖清单**：`requirments.txt`（文件名拼错、只有 4 个包）→ `requirements.txt`，
  补全 Flask / Flask-SocketIO / pynput / psutil / pystray / Pillow / cryptography /
  sherpa-onnx / websocket-client 等。新机器按它装能直接跑。
- `build_exe.bat` 改走 `MovoServer.spec`（原来自己拼参数、产物叫 Movo.exe），
  README 同步。

**待定（没动）**

- `/voice` 独立页与 `templates/voice.html`：语音已整合进三页，这页现在只当调试入口；
  要删的话连 `web_app.voice_page` 一起删。
- `gamepad_service.py`：Code 页已不使用手柄，但服务仍在后台跑 XInput 轮询。
  留着是给以后可能恢复手柄用，删掉能省一个常驻线程。
- 三个模板 CSS/JS 全内联（index.html 89KB 里 CSS 38KB + JS 38KB）：可以外链化让浏览器缓存，
  但改动面大，非必要不动。

## 45. 新版应用图标 + 名称统一为 Movo（App v1.5.1，versionCode 24）

- **图标**：用户选定 AI 生成的浅蓝「手指按蓝色光环触点」图，落地为 Android 自适应图标：
  background = 原图放大 1.4x 裁切轻模糊，foreground = 原图 1:1 铺满 + 边缘 12% 羽化
  （直接缩 66% 会浮一个白方块，羽化后与背景无缝）。5 个密度 mipmap + 删旧 vector。
  同步替换：`static/app-icon.png`（托盘）、`build/app-icon.ico`（exe 打包）、
  三个网页 favicon（touchpad.png / keys.png / controller/favicon.png）。
- **名称**：launcher 名 `app_name`「随动」→「Movo」；keepalive 通知、证书弹窗、
  托盘 tooltip、启动弹窗里的「随动 Movo」统一为「Movo」；页面标题「Movo 随动 | x」
  →「Movo | x」（i18n 中英文 + 4 个模板默认 title）。i18n 的 `welcome.cn: '随动'`
  保留作中文名。
- **注意**：`MovoNative` 桥名、`com.dsnaaa.movo` 包名、`movo_theme` 存储
  键、`MOVO_*` 环境变量**未改也不该改**——内部标识符，改了等于换 App/断桥/丢设置。

## 46. 全量更名 AirMouse → Movo（App v2.0.0，versionCode 25，换包名装机）

用户确认「全都改」。191 处标识符、39 个文件一次替换，手机端换了新包名重装。

**改了什么**

| 类别 | 旧 → 新 |
| --- | --- |
| JS 桥名 | `AirMouseNative` → `MovoNative`（Kotlin 注册处 + 三页模板 + voice/i18n/setup） |
| 包名 | `com.dsnaaa.airmouse` → `com.dsnaaa.movo`（namespace + applicationId + Kotlin 目录搬迁） |
| 本地存储 | `airmouse_theme` / `airmouse_mode` → `movo_*`；SharedPreferences `"airmouse"` → `"movo"` |
| 环境变量 | `AIRMOUSE_NO_TRAY` / `AIRMOUSE_STARTUP_TIP` / `AIRMOUSE_SHOW_CONSOLE` / `AIRMOUSE_DIAG` → `MOVO_*` |
| 脚本名 | `start-airmouse.bat` → `start-movo.bat`，`restart-airmouse.bat` → `restart-movo.bat` |
| 启动项名 | `install-autostart.bat` 现在生成 `Movo.vbs`（旧 `AirMouse.vbs` 待删） |
| 缓存版本 | 静态资源 `?v=` 统一 → `20261028m`，防 WebView 拿旧 JS 找不到新桥 |

**没改的**：上游仓库链接 `cornradio/AirMouse`（readme / CHANGELOG 里的真实 GitHub 地址，
git remote `origin` 同理）。

**装机与数据迁移**

- 包名一改就是新 App：先 `adb run-as` 从旧包导出 `shared_prefs/airmouse.xml`
  （9 个键：url、ui_theme=light、ui_lang、hand_mode=left、gyro_sense、mouse_sense、
  type_delay、fullscreen_mode、**trust_cert**），卸旧装新后 base64 通道原样写回
  `shared_prefs/movo.xml`。实测新 App 首屏即 light 主题 + 原地址直连——设置零丢失。
- WebView 的 localStorage 跨包带不过来，但真源在 prefs（页面经 `getPref` 桥读），
  所以无感。

**目录名没改成（待用户手动）**

`AirMouse` 项目文件夹被 WorkBuddy 会话工作区锁住，会话内 rename 报 Permission denied
（子目录可改、顶层不可改，确认是平台锁）。服务端脚本全部用 `%~dp0` 相对定位，
目录改名不影响功能，改名后重跑一次 `install-autostart.bat` 即可（它现在写 `Movo.vbs`）。


## 47. 双击 exe 弹欢迎/配置页：豆包语音 Key 由用户自己填（本地 5889）

打包的 exe 此前双击后只有一个简陋的 tkinter 提示（甚至可能一闪而过），语音 Key 也只能
手工摆 voice_config.json。现在：

- **新增 `welcome_server.py`**：本地配置服务，绑 `127.0.0.1:5889` 明文 HTTP。
  走 HTTP 而不是复用 5888 的 HTTPS，是因为浏览器对自签证书先弹一页警告，
  第一次用的人还没见到界面就被劝退；只绑回环，局域网访问不到。
- **新增 `templates/welcome.html`**：欢迎页 + 功能简介（触控板/键盘/语音/Code 遥控）+
  API Key 配置。已配置时变成「正在运行」状态卡：显示局域网地址和 Key 尾号。
- **API Key 流程**：填 Key → 「测试连接」（真实做一次 WebSocket 握手，火山在握手阶段
  就校验 Key，401=Key 无效 / 403=没开通 SAUC / 超时=网络问题，分别给不同提示）→
  「保存并完成」写入 `voice_config.json`（0600 权限）并**热生效**——
  `voice_service.reload_cloud_config()` 立即重读，不用重启服务。
- **凭证安全**：`MovoServer.spec` 的 datas 从来没包含 `voice_config.json`
  （只有 templates/static/cert/key），发 exe 不泄露自己的 Key；页面也只回显尾号。
- **双击 / 自启分流**：
  - 双击 exe（无参数）：如果已在运行 → 不起第二实例，直接把浏览器推到设置页后退出；
    首次启动 → 打开欢迎页；浏览器打不开才退回原生小窗。
  - `--silent`（`start-hidden.vbs` 开机自启现在带这个参数）：完全不弹界面，
    否则每次开机都蹦一个网页。
  - 源码模式默认不弹，`MOVO_SETUP_PAGE=1` 可手动打开。
- **托盘菜单**新增「设置 / API Key」入口；顺手修了 `voice_service._load_cloud_config`
  里漏 `global _load_error` 的老 bug。
