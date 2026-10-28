package com.dsnaaa.movo

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.util.Base64
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.webkit.ScriptHandler
import androidx.webkit.WebViewCompat

/**
 * 一个很薄的壳：全屏 WebView 加载电脑上那份页面，再把手机原生能力（震动、常亮、保活）
 * 通过 MovoNative 这个 JS 桥暴露给页面。
 *
 * 这样做的好处：页面仍然是服务端那套 HTML，改完下拉刷新就生效，不用重新打包 APK。
 * 只有真正需要原生的东西（马达、前台服务、以后可能的系统语音识别）才走桥。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var prefs: SharedPreferences

    // 语音输入：WebView 申请麦克风时若系统权限还没给，先挂起这次请求，等系统弹窗的结果
    private var pendingAudioRequest: PermissionRequest? = null

    /** 当前页面是否要求强制全屏（键盘页 /k：一屏按键，不需要状态栏和手势条） */
    private var pageFullscreen = false

    /** document-start 注入的脚本句柄：页面解析前就把系统栏尺寸写进 CSS 变量 */
    private var insScript: ScriptHandler? = null
    private var insScriptKey = ""

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_RECORD_AUDIO) return
        val r = pendingAudioRequest
        pendingAudioRequest = null
        val granted = grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED
        if (r != null) {
            if (granted) r.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) else r.deny()
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        // 允许用 adb 临时指定地址：am start -n ... -e url https://x.x.x.x:5888/touchpad
        intent?.getStringExtra("url")?.takeIf { it.isNotBlank() }?.let { saveUrl(it) }

        // 透明系统栏：内容一直延伸到状态栏/导航栏下面（Android 15 强制边到边），
        // 系统栏本身透明，图标浮在页面底色上；页面用 --sat/--sab/--sal/--sar CSS 变量避让
        // （原生注入真实像素，浏览器里没有变量时走 env() 兜底），显示 / 隐藏由「显示模式」偏好决定。
        WindowCompat.setDecorFitsSystemWindows(window, false)
        applySystemBars()
        // 系统 bar 高度变化（旋转 / 显示模式切换）时，把真实像素推给页面
        val root = findViewById<android.view.ViewGroup>(android.R.id.content)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            lastBars = intArrayOf(bars.left, bars.top, bars.right, bars.bottom)
            installInsStartScript()   // 先保证后续页面加载首帧就带正确变量
            pushBarsToPage()
            insets
        }
        // 当触摸板用的时候屏幕不能自己灭
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        webView = WebView(this).apply {
            // debug 构建开远程调试，方便 chrome://inspect / CDP 排查页面问题
            if (BuildConfig.DEBUG) WebView.setWebContentsDebuggingEnabled(true)
            setBackgroundColor(0xFF000000.toInt())
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                databaseEnabled = true
                mediaPlaybackRequiresUserGesture = false   // 以后做网页录音时要用
                cacheMode = WebSettings.LOAD_DEFAULT
                useWideViewPort = true
                loadWithOverviewMode = false
                builtInZoomControls = false
                displayZoomControls = false
                setSupportZoom(false)
                mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            }
            webViewClient = object : WebViewClient() {
                override fun onReceivedSslError(
                    view: WebView?,
                    handler: SslErrorHandler?,
                    error: SslError?
                ) {
                    // 自签证书：问过一次之后记住，不再打扰
                    if (prefs.getBoolean(KEY_TRUST_CERT, false)) {
                        handler?.proceed()
                    } else {
                        askTrustCert(handler, error?.url ?: "这台电脑")
                    }
                }

                override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                    super.onPageStarted(view, url, favicon)
                    // 键盘页 /k 自带全屏要求：一进页面就藏系统栏，别等加载完再闪一下
                    syncPageFullscreen(url)
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    syncPageFullscreen(url)
                    // 把页面里的 navigator.vibrate 接到原生马达上：现有页面一行都不用改
                    view?.evaluateJavascript(HAPTIC_SHIM, null)
                    // 每次页面加载完都同步一遍系统栏状态（页面 reload 后属性会丢）
                    pushSysBarsToPage()
                    pushBarsToPage()
                }

                override fun onReceivedError(
                    view: WebView?,
                    request: WebResourceRequest?,
                    error: WebResourceError?
                ) {
                    super.onReceivedError(view, request, error)
                    // 主文档加载失败（连不上 / 超时 / 用户拒绝了证书）→ 回设置页提示，
                    // 别让用户对着黑屏发呆。子资源失败不管。
                    if (request?.isForMainFrame == true &&
                        !request.url.toString().startsWith("file://")
                    ) {
                        connectFailed()
                    }
                }
            }
            webChromeClient = object : WebChromeClient() {
                // 页面申请麦克风时转成系统权限（语音输入用）
                // 注意：onPermissionRequest 本身就在主线程，grant/deny 必须当场给，
                // 中间再 post 一次容易让 WebView 判定这次请求已作废（表现就是页面拿到 NotAllowedError）。
                override fun onPermissionRequest(request: PermissionRequest?) {
                    val r = request ?: return
                    val audio = r.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)
                    when {
                        !audio -> r.deny()
                        checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                            PackageManager.PERMISSION_GRANTED ->
                            r.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                        // 权限还没给：先向系统要，弹窗结果回来再放行给 WebView
                        else -> {
                            pendingAudioRequest = r
                            requestPermissions(
                                arrayOf(Manifest.permission.RECORD_AUDIO), REQ_RECORD_AUDIO
                            )
                        }
                    }
                }
            }
            addJavascriptInterface(AppBridge(this@MainActivity, this), "MovoNative")
        }

        setContentView(webView)
        // 必须先 setContentView：apply{} 里 webView 还没赋值，且 insets 回调要到第一帧才来，
        // 这里用系统资源里的状态栏高度先装上，保证 onCreate 末尾的首次 loadUrl 就已生效
        installInsStartScript()

        // 麦克风权限提前要：等到用户按住圆钮才弹系统窗，手指往往已经松开，
        // 而且 WebView 那次 request 还可能超时，表现就是「按了没反应」。
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            webView.postDelayed({
                requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_RECORD_AUDIO)
            }, 1000)
        }

        // 路由：第一次启动（还没存地址）→ 欢迎/配置页；已存地址 → 探测通了直接进触控板，
        // 探测不通（比如不在同一网段）立刻回设置页提示，绝不黑屏干等。
        // 调试：adb shell am start -n .../.MainActivity -e setup welcome|settings 可强制打开配置页
        when (intent?.getStringExtra("setup")) {
            "settings" -> loadSetup("settings")
            "welcome" -> loadSetup("welcome")
            else -> {
                val saved = prefs.getString(KEY_URL, null)
                if (saved.isNullOrBlank()) loadSetup("welcome") else tryConnectOrSetup(saved)
            }
        }
    }

    /**
     * 启动时的快速连通性探测：后台线程 TCP 连一下服务端口，1.5 秒内通就进触控板
     * （同网段基本是毫秒级，无感）；不通就不再发起那次会卡死几十秒的 WebView 加载，
     * 直接回设置页弹「连不上」，用户改完地址点确定重试。
     */
    private fun tryConnectOrSetup(url: String) {
        Thread {
            val ok = runCatching {
                val u = java.net.URI(url)
                val port = if (u.port > 0) u.port else 443
                java.net.Socket().use { s ->
                    s.connect(java.net.InetSocketAddress(u.host, port), 1500)
                    true
                }
            }.getOrDefault(false)
            runOnUiThread {
                if (ok) webView.loadUrl(url) else loadSetup("settings", "connect")
            }
        }.start()
    }

    /** 配置页是打进 APK 的本地页（assets/setup.html），断网/地址填错时也能打开来改 */
    fun loadSetup(mode: String) {
        loadSetup(mode, null)
    }

    /** err 非空时设置页会弹「连不上」提示（err=connect） */
    fun loadSetup(mode: String, err: String?) {
        runOnUiThread {
            val theme = prefs.getString(PREF_THEME, null)
            val t = if (theme == "light" || theme == "dark") "&t=$theme" else ""
            val e = if (err.isNullOrBlank()) "" else "&err=$err"
            webView.loadUrl("file:///android_asset/setup.html?mode=$mode$t$e")
        }
    }

    /** 连不上电脑：别黑屏，回到设置页让用户改地址/重试 */
    fun connectFailed() {
        loadSetup("settings", "connect")
    }

    fun currentUrl(): String =
        prefs.getString(KEY_URL, null) ?: BuildConfig.DEFAULT_URL

    fun loadSaved() {
        runOnUiThread { webView.loadUrl(currentUrl()) }
    }

    fun prefString(key: String): String = prefs.getString(key, "") ?: ""

    fun putPref(key: String, value: String) {
        prefs.edit().putString(key, value).apply()
    }

    /** 按设置的「显示模式」+ 当前页面的强制全屏要求，显示 / 隐藏系统栏（状态栏 + 导航栏） */
    fun applySystemBars() {
        val fullscreen = pageFullscreen || prefString("fullscreen_mode") == "on"
        val c = WindowInsetsControllerCompat(window, window.decorView)
        if (fullscreen) {
            c.hide(WindowInsetsCompat.Type.systemBars())
            c.systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        } else {
            // 系统栏透明（Android 15 边到边下背景本来就是透明的），只调图标明暗：
            // 日间页面底色浅，状态栏图标要用深色才看得见
            val light = prefString("ui_theme") == "light"
            c.isAppearanceLightStatusBars = light
            c.isAppearanceLightNavigationBars = light
            c.show(WindowInsetsCompat.Type.systemBars())
        }
        pushSysBarsToPage()
        installInsStartScript()
    }

    /** 键盘页（/k）永远全屏；其它页面听设置里的「显示模式」 */
    private fun syncPageFullscreen(url: String?) {
        if (url.isNullOrBlank()) return
        val path = runCatching { java.net.URI(url).path ?: "" }.getOrDefault("")
        val kb = path == "/k" || path.startsWith("/k/")
        if (kb == pageFullscreen) return
        pageFullscreen = kb
        applySystemBars()
    }

    /** 告诉页面当前系统栏状态：html[data-sysbars="on"]，页面 CSS 据此做顶部避让 */
    private fun pushSysBarsToPage() {
        // onCreate 前 / App 退出时 webView 还没建好，跳过即可；页面加载完会再同步一次
        if (!this::webView.isInitialized) return
        val on = !(pageFullscreen || prefString("fullscreen_mode") == "on")
        webView.evaluateJavascript(
            "document.documentElement.setAttribute('data-sysbars','" +
                (if (on) "on" else "off") + "')", null
        )
    }

    /** WebView 里 env(safe-area-inset-*) 对状态栏不可靠，原生直接把真实像素注入 CSS 变量：
        --satop / --sabottom / --saleft / --saright（浏览器里没有这些变量，页面走 env() 兜底） */
    private var lastBars: IntArray? = null

    /** 首帧还没收到 insets 时，用系统资源里的状态栏 / 导航栏高度先顶一下 */
    private fun sysBarPx(name: String): Int {
        val id = resources.getIdentifier(name, "dimen", "android")
        return if (id > 0) resources.getDimensionPixelSize(id) else 0
    }

    /**
     * 在文档开始解析之前就把系统栏尺寸写进 html 的 CSS 变量。
     *
     * 只在 onPageFinished / insets 回调里注入不够：页面会先按「没有系统栏」排好版
     * （触控板 6px），等注入到了才跳到 47px——从 coding 页、设置页返回主页时
     * 表现为整页往下抖一下（每次返回都是一次新的页面加载，首帧必然没有变量）。
     * document-start 注入早于任何页面脚本和首次绘制，第一帧就是最终位置。
     */
    private fun installInsStartScript() {
        if (!this::webView.isInitialized) return
        val d = resources.displayMetrics.density
        val bars = lastBars ?: intArrayOf(
            0, sysBarPx("status_bar_height"), 0, sysBarPx("navigation_bar_height")
        )
        val on = !(pageFullscreen || prefString("fullscreen_mode") == "on")
        fun px(v: Int) = Math.round(v / d)
        val l = px(bars[0])
        val t = px(bars[1])
        val r = px(bars[2])
        val b = px(bars[3])
        val key = "$l,$t,$r,$b,$on"
        if (key == insScriptKey && insScript != null) return
        insScriptKey = key
        val js = "(function(){var S={l:'${l}px',t:'${t}px',r:'${r}px',b:'${b}px'," +
            "s:'${if (on) "on" else "off"}'};" +
            "function a(){var d=document.documentElement;if(!d)return false;" +
            "d.style.setProperty('--saleft',S.l);d.style.setProperty('--satop',S.t);" +
            "d.style.setProperty('--saright',S.r);d.style.setProperty('--sabottom',S.b);" +
            "d.setAttribute('data-sysbars',S.s);return true;}" +
            "if(!a()){var m=new MutationObserver(function(){if(a())m.disconnect();});" +
            "m.observe(document,{childList:true,subtree:true});}})()"
        insScript?.remove()
        // 老 WebView / 未开启该特性时可能抛异常，失败就退回 onPageFinished 注入（会抖但能用）
        insScript = runCatching {
            WebViewCompat.addDocumentStartJavaScript(webView, js, setOf("*"))
        }.getOrNull()
    }

    private fun pushBarsToPage() {
        if (!this::webView.isInitialized) return
        val b = lastBars ?: return
        val d = resources.displayMetrics.density
        val js = "var de=document.documentElement.style;" +
            "de.setProperty('--saleft','${Math.round(b[0] / d)}px');" +
            "de.setProperty('--satop','${Math.round(b[1] / d)}px');" +
            "de.setProperty('--saright','${Math.round(b[2] / d)}px');" +
            "de.setProperty('--sabottom','${Math.round(b[3] / d)}px')"
        webView.evaluateJavascript(js, null)
    }

    private fun askTrustCert(handler: SslErrorHandler?, host: String) {
        AlertDialog.Builder(this)
            .setTitle(R.string.cert_title)
            .setMessage(getString(R.string.cert_msg, host))
            .setPositiveButton(R.string.cert_trust) { _, _ ->
                prefs.edit().putBoolean(KEY_TRUST_CERT, true).apply()
                handler?.proceed()
            }
            .setNegativeButton(R.string.cert_cancel) { _, _ -> handler?.cancel() }
            .setCancelable(false)
            .show()
    }

    // 返回键语义：按「页面层级」退一层，不再看网页历史。
    //   触控板（主页）→ 直接回手机桌面
    //   其它页面（键盘 / coding / 设置）都是主页的二级页 → 一律回主页，不退出
    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (!this::webView.isInitialized) {
            super.onBackPressed()
            return
        }
        if (isHomePage()) {
            // 主页按返回就是回桌面，不用再按两次
            moveTaskToBack(true)
        } else {
            goHome()
        }
    }

    /** 当前页面是不是触控板主页（/touchpad） */
    private fun isHomePage(): Boolean {
        val url = webView.url ?: return false
        val path = runCatching { android.net.Uri.parse(url).path ?: "" }.getOrDefault("")
        return path == "/touchpad" || path == "/touchpad/"
    }

    /** 回到触控板主页；地址还没配置（首次欢迎页）时没有主页可回，直接退到桌面 */
    private fun goHome() {
        if (prefs.getString(KEY_URL, null).isNullOrBlank()) {
            moveTaskToBack(true)
            return
        }
        val url = webView.url ?: ""
        if (url.startsWith("file://")) {
            // 设置页是本机资产页，走统一的加载入口
            loadSaved()
        } else {
            // 键盘页 / coding 页同为 https 页面，同源跳转更平滑
            webView.evaluateJavascript("location.replace('/touchpad')", null)
        }
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
        // 从后台切回来时系统可能把系统栏放出来了，按当前页面的规则再收一遍
        applySystemBars()
    }

    override fun onPause() {
        webView.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        stopNativeMic()
        webView.destroy()
        super.onDestroy()
    }

    // ---------- 原生录音兜底 ----------
    // WebView 的 getUserMedia 在某些机型 / 自签证书环境下会直接 NotAllowedError，
    // 权限明明给了也拿不到流。这里直接用 AudioRecord 采音（16k / 单声道 / PCM16），
    // 每 100ms 把一小包 base64 丢给页面，页面塞进同一条 voice_audio 通道，
    // 服务端一行都不用改。
    private var audioRecord: AudioRecord? = null
    private var micThread: Thread? = null

    @Volatile
    private var micRunning = false

    /** 返回 "ok" 或失败阶段（perm / init / start:xxx / new:xxx），页面据此提示 */
    fun startNativeMic(): String {
        if (micRunning) return "ok"
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            // JS 桥回调不在 UI 线程，申请权限必须回主线程
            runOnUiThread {
                requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_RECORD_AUDIO)
            }
            return "perm"
        }
        val minBuf = try {
            AudioRecord.getMinBufferSize(
                MIC_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
            )
        } catch (e: Throwable) {
            -1
        }
        val rec = try {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION, MIC_RATE,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                if (minBuf > MIC_CHUNK * 4) minBuf else MIC_CHUNK * 4
            )
        } catch (e: Throwable) {
            return "new:" + e.javaClass.simpleName
        }
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release()
            return "init"
        }
        try {
            rec.startRecording()
        } catch (e: Throwable) {
            rec.release()
            return "start:" + e.javaClass.simpleName
        }
        audioRecord = rec
        micRunning = true
        micThread = Thread {
            val buf = ByteArray(MIC_CHUNK)
            while (micRunning) {
                val n = try {
                    rec.read(buf, 0, buf.size)
                } catch (e: Throwable) {
                    -1
                }
                if (n < 0) break
                if (n == 0) continue
                val b64 = Base64.encodeToString(buf, 0, n, Base64.NO_WRAP)
                webView.post {
                    webView.evaluateJavascript(
                        "window.__nativePcm&&window.__nativePcm('$b64')", null
                    )
                }
            }
        }.also { it.start() }
        return "ok"
    }

    fun stopNativeMic() {
        micRunning = false
        try {
            audioRecord?.stop()
        } catch (e: Exception) {
        }
        try {
            audioRecord?.release()
        } catch (e: Exception) {
        }
        audioRecord = null
        micThread = null
    }

    fun saveUrl(url: String) {
        prefs.edit().putString(KEY_URL, url).apply()
    }

    fun setKeepScreenOn(on: Boolean) {
        runOnUiThread {
            if (on) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }

    /** 前台服务：让 WebView 进程不被冻结，socket 在切后台后仍然活着 */
    fun setKeepAlive(on: Boolean) {
        val i = Intent(this, KeepAliveService::class.java)
        runOnUiThread {
            if (on) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(i)
                else startService(i)
            } else {
                stopService(i)
            }
        }
    }

    companion object {
        const val PREFS = "movo"
        const val KEY_URL = "url"
        const val KEY_TRUST_CERT = "trust_cert"
        const val PREF_THEME = "ui_theme"   // 网页端切换主题时同步写进来
        const val REQ_RECORD_AUDIO = 41
        const val MIC_RATE = 16000          // 和服务端 / 火山豆包一致
        const val MIC_CHUNK = 3200          // 1600 个采样 = 100ms
    }
}

/**
 * 页面里能放心调用的原生接口。方法名保持简短，JS 侧写起来顺。
 */
class AppBridge(private val activity: MainActivity, private val webView: WebView) {

    @JavascriptInterface
    fun haptic(kind: String) {
        activity.runOnUiThread { Haptics.play(activity, kind) }
    }

    @JavascriptInterface
    fun tick() {
        activity.runOnUiThread { Haptics.tick(webView) }
    }

    /** 试听页用：按名字播放任意 HapticFeedbackConstants 等级。
     *  返回值 = 这台机器有没有这个常量（playConst 是异步投递到 UI 线程的，拿不到它的返回值） */
    @JavascriptInterface
    fun hapticConst(name: String, force: Boolean): Boolean {
        val exists = Haptics.constId(name) >= 0
        activity.runOnUiThread { Haptics.playConst(webView, name, force) }
        return exists
    }

    @JavascriptInterface
    fun hapticConstList(): String = Haptics.constList()

    /** 只查支持性，不震 —— 用 hapticConst() 代替它做探测会多震一下 */
    @JavascriptInterface
    fun hapticConstExists(name: String): Boolean = Haptics.constId(name) >= 0

    @JavascriptInterface
    fun vibrateInfo(): String = Haptics.info(activity)

    @JavascriptInterface
    fun keepAwake(on: Boolean) = activity.setKeepScreenOn(on)

    @JavascriptInterface
    fun keepAlive(on: Boolean) = activity.setKeepAlive(on)

    @JavascriptInterface
    fun setUrl(url: String) = activity.saveUrl(url)

    /** 兼容别名：setup 页一直调用的是 saveUrl，桥里只有 setUrl 会导致地址永远存不进去 */
    @JavascriptInterface
    fun saveUrl(url: String) = activity.saveUrl(url)

    /** 配置页用：当前已保存的地址（没存过就是编译期默认值） */
    @JavascriptInterface
    fun currentUrl(): String = activity.currentUrl()

    /** 配置页用：保存完地址直接进触控板 */
    @JavascriptInterface
    fun goTouchpad() = activity.loadSaved()

    /** 触控板 ⋮ 菜单用：打开设置页 */
    @JavascriptInterface
    fun openSettings() = activity.loadSetup("settings")

    @JavascriptInterface
    fun getPref(key: String): String = activity.prefString(key)

    @JavascriptInterface
    fun setPref(key: String, value: String) {
        activity.putPref(key, value)
        // 网页端切主题时同步系统栏图标明暗（日间深色图标 / 夜间白色图标）
        if (key == "ui_theme") activity.runOnUiThread { activity.applySystemBars() }
    }

    /** 设置页改完「显示模式」立即生效：重新按 fullscreen_mode 应用系统栏 */
    @JavascriptInterface
    fun applyFullscreen() {
        activity.runOnUiThread { activity.applySystemBars() }
    }

    @JavascriptInterface
    fun reload() {
        activity.runOnUiThread { webView.reload() }
    }

    @JavascriptInterface
    fun version(): String = BuildConfig.VERSION_NAME

    /** 原生录音兜底：WebView 的 getUserMedia 拿不到麦克风时用这个顶上 */
    @JavascriptInterface
    fun startMic(): String = activity.startNativeMic()

    @JavascriptInterface
    fun stopMic() = activity.stopNativeMic()

    @JavascriptInterface
    fun isNative(): Boolean = true
}

private const val HAPTIC_SHIM = """
(function(){
  if (!window.MovoNative) return;
  var original = navigator.vibrate;
  navigator.vibrate = function(p){
    try {
      // 其它子页面（键盘/语音/按键/手柄）还在用 navigator.vibrate(30)，
      // 统一走实测选定的 VIRTUAL_KEY，手感和触控板保持一致
      window.MovoNative.hapticConst('VIRTUAL_KEY', false);
      return true;
    } catch (e) {
      return original ? original.call(navigator, p) : false;
    }
  };
})();
"""
