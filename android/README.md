# Movo 安卓 App（WebView 壳）

一个**薄壳**：全屏 WebView 加载电脑上那份 `templates/index.html`，再把手机原生能力通过
`MovoNative` 这个 JS 桥暴露给页面。

## 为什么是壳，不是纯原生

| | 纯原生重写 | 这个壳 |
|---|---|---|
| 改一个按钮位置 | 改代码 → 重新构建 → 重新安装 | 改 HTML → 手机下拉刷新 |
| 触控板/输入条/滚动条/主题 | 全部重写（约 1–2 周） | 一行不用改 |
| 原生震动 | 有 | 有（走桥） |
| 后台保活 | 有 | 有（前台服务） |
| 语音识别 | 有 | 有（v2 接入） |

结论：先把壳做出来，把"原生才能做的事"逐件搬过去。等哪天真的嫌 WebView 卡了，再一块块换成 Compose，
页面和原生可以共存（同一个 App 里混排）。

---

## 一、环境配置（换到新电脑，从零开始）

### 1. JDK 17

AGP 8.x 要求 **JDK 17**（不是 8，也不是 21 更稳）。这台机器上已经有了：

```
java -version   → openjdk 17.0.21
JAVA_HOME       = C:\Program Files\Java\jdk-17.0.21.0.2+1
```

新机器如果没有，装 Temurin 17 或让 Android Studio 用它自带的 JBR（Studio 内嵌的运行时也能编译）。

### 2. Android Studio（推荐，省掉一堆手工步骤）

装当前稳定版即可（≥ Ladybug / 2024.2）。它自带 SDK Manager、模拟器、Gradle 下载器。

如果只想用命令行，装 **Command-line Tools** 就够：

```
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
```

### 3. 环境变量

```
ANDROID_HOME = %LOCALAPPDATA%\Android\Sdk
PATH        += %ANDROID_HOME%\platform-tools
```

设完开新终端验证：`adb version`（这台机器已有 `C:\Program Files\Android\platform-tools\adb.exe`，
版本 1.0.41 / 37.0.1，够用）。

### 4. Gradle

**已经生成好 wrapper 了**，不需要单独装 Gradle，直接用 `gradlew.bat`。

> 本机（2026-10-27）已配好：SDK 在 `C:\Users\fantasy\AppData\Local\Android\Sdk`，
> 独立 Gradle 8.9 在 `C:\Users\fantasy\Apps\gradle-8.9`，代理写在 `~\.gradle\gradle.properties`。
> 换新机器时把这两处路径对应改一下，或者让 Android Studio 自己下。

> 国内网络下载 Gradle 和依赖慢的话，把代理写进 `android/gradle.properties`：
> ```
> systemProp.https.proxyHost=192.168.31.100
> systemProp.https.proxyPort=7893
> ```

### 5. 小米 15 开调试

1. 设置 → 我的设备 → 全部参数与信息 → **连点「OS 版本」7 次**，开启开发者模式
2. 设置 → 更多设置 → 开发者选项 → 打开 **USB 调试**
3. 同一页打开 **USB 安装**（HyperOS 默认关，开启时需要登录小米账号）
4. 同一页可以顺手关掉「日志缓冲器大小」之类的干扰项，不影响
5. 数据线连电脑，手机上弹出「允许 USB 调试吗」→ 勾"一律允许"

没有线也可以用**无线调试**（Android 11+）：

```
设置 → 开发者选项 → 无线调试 → 使用配对码配对设备
adb pair 192.168.31.70:41234     # 手机屏幕上显示的 IP:端口 + 六位码
adb connect 192.168.31.70:5555
adb devices                      # 应该能看到设备
```

---

## 二、构建与安装

```bat
cd Movo\android

gradlew.bat assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
adb shell am start -n com.dsnaaa.movo/.MainActivity

:: 换电脑后 IP 变了，不用重新打包，直接覆盖地址：
adb shell am start -n com.dsnaaa.movo/.MainActivity -e url https://192.168.31.99:5888/touchpad
```

APK 位置：`android/app/build/outputs/apk/debug/app-debug.apk`（首次构建约 3–5 分钟，
要下 Gradle 8.9 + AGP + AndroidX，走代理大约 200MB）。

第一次打开会弹一个「这是自签名证书」的对话框，点**信任并记住**，之后不再问。
（根因是 `cert.pem` 没被手机信任，见第三节最后一条。）

---

## 三、小米 15 / HyperOS 适配清单

| 项目 | 说明 | 已处理 |
|---|---|---|
| 屏幕 1200×2670，约 460dpi，比例 2.225 | 页面用 `width=device-width` 即可；但**底部手势条会压住按键栏** | ✅ 页面已加 `env(safe-area-inset-bottom)` |
| 挖孔前摄 | `windowLayoutInDisplayCutoutMode=shortEdges`，内容可延伸进挖孔区 | ✅ |
| 120Hz LTPO | `touchpad.js` 里每个 `touchmove` 都 emit 一次，120Hz 下最高 120 次/秒，会浪费带宽也让光标抖 | ✅ 已改成按 `requestAnimationFrame` 合帧发送 |
| 手势导航 | 沉浸式已隐藏状态栏/手势条，上滑临时唤出；从屏幕最底部上滑仍可能被系统接管 | ✅（用上滑手势时要抬高一点起手） |
| 锁屏 / 通知 | 前台服务需要 `POST_NOTIFICATIONS` 运行时授权（Android 13+） | 待 v3 首次启动时申请 |
| **HyperOS 省电策略** | 默认会杀后台，前台服务也可能被杀 | ⚠️ **必须手动设**：设置 → 应用设置 → 应用管理 → Movo → 省电策略 → **无限制**；同一页的「自启动」也打开 |
| 最近任务清理 | 一键清理会把进程带走 | 在最近任务里长按 Movo 卡片 → 锁定 |
| 自签名证书 | 每次弹信任框 | App 内弹一次并记住；想彻底干净就装 CA（见下） |
| WebView 内核 | HyperOS 用系统 Chrome 内核，跟随 Chrome 更新 | 保持 Chrome 更新即可，不用打包内核 |
| X 轴线性马达 | 小米 15 马达素质够，`EFFECT_TICK` 很干脆 | ✅ `Haptics.kt` |

**关于证书**：App 的 `network_security_config.xml` 已经允许"用户安装的 CA"。想彻底消掉信任框，
就生成一套本地 CA、给 `192.168.31.12` 签一张带 IP 的证书，把 CA 装进手机
（设置 → 安全 → 更多安全设置 → 加密与凭据 → 安装证书 → CA 证书）。顺带浏览器里那个警告页也会消失。

---

## 四、页面侧配合改动

1. **底部安全区** ✅ 已改：`#bottom-nav` 用 `calc(75px + env(safe-area-inset-bottom))`，
   浏览器里 env() 为 0，不影响网页版。
2. **移动事件合帧** ✅ 已改：`static/js/touchpad.js` 的 `emit('move')` 改成攒到下一帧发一次，
   高刷屏上注册的 emit 次数直接减半以上。
3. **震动语义化**（可选）：现在是 `navigator.vibrate(30)` 一刀切，App 里会被自动映射成 `click`。
   想更细就显式调用：

```js
const nativeHaptic = (kind) => window.MovoNative?.haptic(kind);

// 左键按下
nativeHaptic('click');
// 右键 / 切模式
nativeHaptic('heavy');
// 滚轮每滚 3 格震一下（别每格都震，会手麻）
nativeHaptic('scroll');
// 边缘滚动条被按住/松开
nativeHaptic('tick');
```

---

## 五、三期路线

**v1 壳（半天）** —— 已完成，`gradlew.bat assembleDebug` 构建通过，产物 3.2MB
- 全屏 WebView + 原生震动 + 屏幕常亮 + 自签证书信任

**v2 语音（1 天）**
- 先探测系统识别：`SpeechRecognizer.isOnDeviceRecognitionAvailable()` / `RecognizerIntent`。
  小米国内 ROM 没 GMS，**大概率不可用**，探测不到就走第二条。
- 主路线：WebView 里 `MediaRecorder` 录音 → `POST /asr` 给电脑 → 服务端 `sherpa-onnx + Paraformer`
  识别 → `type_text` 注入。手机端只是"按住 🎤 说话、松手出字"，全程不弹键盘。

**v3 打磨（半天）**
- 前台服务保持连接（`KeepAliveService` 已在，接线即可）
- 设置页：改服务器地址、震动强度、是否常亮
- release 签名：`keytool -genkey -v -keystore movo.jks -keyalg RSA -keysize 2048 -validity 10000 -alias movo`，
  在 `app/build.gradle.kts` 里配 `signingConfigs`

---

## 六、已知坑

- **`local.properties` 不能提交**，里面是本机 SDK 路径，Android Studio 打开时自动生成（已 gitignore）。
- **AGP 8.x 必须 JDK 17**，用 JDK 8 或 11 会直接报 `Unsupported class file major version`。
- **HyperOS 的「USB 安装」默认关闭**，`adb install` 会报 `INSTALL_FAILED_USER_RESTRICTED`，
  去开发者选项里打开，或者每次安装时在手机上点"允许"。
- **`adb devices` 显示 unauthorized**：手机上没点"允许调试"，拔线重插。
- WebView 里 `console.log` 看不到，调试用电脑 Chrome 打开 `chrome://inspect`。
