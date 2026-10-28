# Movo（Remote Pro）部署与开发指南

手机浏览器当电脑的无线触控板 + 键盘：HTTPS 局域网服务，手机扫码或输地址连接，
支持触控板、实体键模拟、快捷文字输入（含输入法语音）、右边缘滚轮、日/夜间主题。

- 服务端口：**5888**（HTTPS，自签名证书）
- 技术栈：Python + Flask + flask-socketio + pynput（键鼠注入）+ sherpa-onnx / 火山豆包（语音）
- 平台：Windows（pynput 键鼠注入、托盘图标）

---

## 一、换新电脑：5 步跑起来

1. **装 Python 3.10 及以上**（python.org 安装包，勾选 *Add python.exe to PATH*）。
2. 把整个 `Movo` 文件夹放到一个**固定位置**（例如 `C:\Apps\Movo`，
   不要放在临时目录，启动项里写的是绝对路径）。
3. 双击 **`setup-new-pc.bat`**
   - 网络受限时用代理：`setup-new-pc.bat 192.168.31.100:7893`（脚本会自动加 `http://`）。
   - 它会创建 `.venv` 并安装 `requirements.txt` 里的全部依赖。
4. 双击 **`start-movo.bat`** 启动（带黑窗口，方便看日志）。
   启动后窗口会打印所有可用地址，找带 `[推荐]` 标记的那个（WLAN 网卡 IP）。
5. 手机连**同一 WiFi**，浏览器打开 `https://<电脑IP>:5888/`。
   首次会有证书警告（自签名），点「继续访问」即可。

> **证书说明**：zip 包里自带 `cert.pem` / `key.pem`（自签名，10 年有效）。
> 若是**从 Git 仓库克隆**的（仓库不入库证书），先执行
> `.venv\Scripts\python.exe regen-cert.py` 生成一对再启动。
> 若想换新的，同样运行 `regen-cert.py`。
> 手机上如果不小心点了「不信任」，到浏览器设置里清除该站点数据再重进。

### 开机自启（可选，推荐）

双击 **`install-autostart.bat`**：它会在
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` 下生成一个 `Movo.vbs` 薄壳，
指向**当前文件夹**里的 `start-hidden.vbs`，登录即静默启动，无窗口、无需管理员。

- ⚠️ **启动项里写的是绝对路径**。以后如果把 Movo 文件夹挪了位置，
  必须在新位置**再跑一次** `install-autostart.bat`，否则开机就会报
  “Python not found”。
- ⚠️ 新电脑解压后必须先跑 `setup-new-pc.bat` 建 `.venv`，否则同样报
  “Python not found”（启动项找的是 `Movo\.venv\Scripts\pythonw.exe`）。
- 取消自启：双击 `remove-autostart.bat`，或直接删掉启动文件夹里那个 vbs。

### 开机免输入密码（自动登录，可选）

先说结论：**服务必须等进入桌面之后才能真正控制键鼠**——鼠标/键盘注入需要一个
交互式桌面会话，锁屏/登录界面下注入无效，所以“不登录就能用”做不到。
但可以让系统**开机自动登录**，跳过输入密码这一步：

1. 以管理员身份运行 **`enable-autologon.bat`**，按提示输入 Windows 用户名和密码
   （如果平时用 PIN 登录，这里填**账户密码**，不是 PIN）。
2. 重启验证：开机 → 自动进桌面 → 启动项拉起服务，全程无需输入。
3. 想恢复登录界面：管理员运行 **`disable-autologon.bat`**。

⚠️ 注意：开了自动登录后，**任何能按下电源键的人都能直接进你的桌面**。
只在信任的私人电脑上用；密码会以明文存在注册表 Winlogon 项里。

### 防火墙

首次启动若弹出防火墙授权，选择「允许（专用网络）」。
也可以手动放行：管理员 PowerShell 执行

```powershell
New-NetFirewallRule -DisplayName "movo" -Direction Inbound -Protocol TCP -LocalPort 5888 -Action Allow
```

---

## 二、目录结构与脚本一览

```
Movo/
├─ server.py              服务入口（端口 5888、托盘、证书加载）
├─ web_app.py             Flask 路由 + SocketIO（已开模板热重载）
├─ keyboard_service.py    键盘注入（tap_key / key_action / 组合键 / release_all）
├─ mouse_service.py       鼠标注入（移动 / 滚轮 / 按键）
├─ gamepad_service.py     手柄映射页的后端
├─ config_manager.py      特殊键名 → pynput Key 的映射表
├─ app_paths.py           资源路径处理（兼容 pyinstaller 打包）
├─ release_keys.py        【救急】释放所有可能卡住的按键
├─ regen-cert.py          重新生成自签名证书
├─ requirements.txt       依赖清单（flask / flask-socketio / pynput / psutil / pystray / pillow / cryptography / sherpa-onnx）
│
├─ templates/             全部页面（改完刷新手机即可，无需重启）
│   ├─ index.html         触控板主页（输入条、边缘滚轮、主题切换都在这）
│   ├─ keyboard.html      键盘页 /k
│   ├─ controller.html    Code 页 /controller
│   ├─ voice.html         语音调试页 /voice（正常使用走三页内的话筒）
│   └─ ...
├─ static/                前端 js / 图标
├─ gyro/                  陀螺仪调试页（上游遗留，无路由，仅存档）
├─ img/                   截图
├─ build/                 pyinstaller 打包产物（可不迁移）
│
├─ start-movo.bat     前台启动（带窗口看日志；已在跑会提示，不报错）
├─ restart-movo.bat   一键 kill 5888 占用进程并重启
├─ start-hidden.vbs       静默启动（无窗口，开机启动项指向它）
├─ install-autostart.bat  安装开机自启（生成启动项薄壳，指向本文件夹）
├─ remove-autostart.bat   卸载自启 + 停止服务
├─ enable-autologon.bat   开机自动登录（免输密码，需管理员，见「开机免输入密码」）
├─ disable-autologon.bat  恢复登录界面
├─ setup-new-pc.bat       新电脑一键建 venv + 装依赖
```

## 三、日常使用与开发约定

- **改 `templates/*.html` 不用重启**：`web_app.py` 已开 `TEMPLATES_AUTO_RELOAD`，
  改完手机下拉刷新即可。只有改 `.py` 才需要重启（双击 `restart-movo.bat`）。
- 重启会让手机 socket 断线几秒，尽量少重启。
- 服务默认隐藏控制台 + 托盘图标。调试时可用环境变量：
  `MOVO_SHOW_CONSOLE=1`（显示控制台）、`MOVO_NO_TRAY=1`（不建托盘）。
- 新电脑的 IP 会变，启动窗口打印的 `[推荐]` 地址就是最新的。

## 四、键盘安全机制（重要，血泪教训）

任何「按下/松开」配对，**服务端必须保证最终一定 release**，不能依赖手机端按时发 up：

- 短按（退格、回车、键盘页单击）一律走 socket 事件 **`tap_key`**
  （`keyboard_service.handle_tap`：press → 15ms → release，无线程无竞态）。
- 只有真正的「按住连发」（修饰键锁、长按方向键）才用 `key_action` down/up；
  其重复线程全程 `try/finally: keyboard.release(...)`。
- 手机每次连上（socket connect）服务端自动 `release_all()` 复位按键。
- **键位错乱、物理键盘像被按住修饰键时**：项目根目录执行
  `.venv\Scripts\python.exe release_keys.py`，或重启电脑。

## 五、触控板页（index.html）功能备忘

- 布局：顶部图标栏 → `#qi-bar` 快捷输入条（输入框 + ⌫ + ⏎）→ `#pad`
  （右缘 `#scroll-edge` 滚轮条）→ 底部鼠标按键/灵敏度栏。
- 输入条：停 600ms 自动 `type_text` 发送并清空；回车立即发；⌫ 框里有字先删自己、
  空了删电脑上的；⏎ 先把框里的字发出去再给电脑敲回车。`compositionstart/end` 守卫拼音组词。
- 边缘滚轮条（36px）：`touchstart/move` 必须 `stopPropagation()`，
  否则会被触控板当成滑动/点击；每 12px 一格（`SE_STEP`）。
- 主题：CSS 变量，`:root` 夜间 / `html[data-theme="light"]` 日间；
  记忆键 `localStorage.movo_theme`；head 内联脚本在首绘前设置避免闪色。
  **新增颜色一律走变量**，不要写死色值。其它子页（/k /controller）尚未接入主题。
- 输入框聚焦会暂停陀螺仪，blur 恢复；`handleFirstInteraction` 里有 `closest('#qi-bar')` 守卫。

## 六、常见问题

| 现象 | 处理 |
|---|---|
| 双击启动闪退 / 端口报 10048 | 已有实例在跑。用 `restart-movo.bat` 重启，或先 `netstat -ano \| findstr :5888` 找 PID kill |
| 手机打不开页面 | 确认同一 WiFi、防火墙放行 5888、地址是启动窗口打印的 `[推荐]` IP |
| 证书警告反复出现 | 正常（自签名）。继续访问；介意可把证书装进手机并信任 |
| 键位全乱 / 打字变快捷键 | `.venv\Scripts\python.exe release_keys.py`，不行就重启电脑 |
| 改了页面没生效 | 手机强制刷新；确认改的是 `templates/` 下对应文件 |
| 语音输入 | 直接用手机输入法自带的 🎤（点输入条弹键盘后按输入法语音键），说完自动上屏、停顿后自动发到电脑 |

## 七、打包成 exe（可选）

`build_exe.bat`（内部用 pyinstaller，产物在 `build/`）。换新电脑开发时**不需要** build 目录，
需要分发免安装版时再重新打包。
