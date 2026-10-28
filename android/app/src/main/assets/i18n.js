/* ============================================================
   Movo 中英文词表 + 应用器
   用法：
     <span data-i18n="pad.mode.pad">触摸板</span>
     <input data-i18n-ph="pad.ph" placeholder="...">
     <button data-i18n-title="pad.send" data-i18n-aria="pad.send">
   脚本里：MovoLang.t('cp.toast.sent', cmd)
   切语言：MovoLang.set('en')  // 会写 pref: ui_lang 并立即重刷本页
   语言来源顺序：?lang= → App 原生偏好 ui_lang → localStorage.movo_lang → 中文
   ============================================================ */
(function () {
    var D = {
        zh: {
            /* ---------- 通用 ---------- */
            'app.title.pad': 'Movo | 触控板',
            'app.title.kb': 'Movo | 键盘',
            'app.title.cp': 'Movo | Code',
            'conn.offline': '未连接 · 点此刷新',
            'conn.sleep': '已休眠 · 轻触屏幕唤醒',
            'conn.waking': '正在连接…',
            'common.back': '返回',
            'common.cancel': '取消',
            'common.save': '保存',
            'common.backhome': '返回主页',
            'common.saved': '已保存',

            /* ---------- 触控板页 ---------- */
            'pad.kb': '键盘模式',
            'pad.settings': '设置',
            'pad.ph': '打字或语音，停一下就发',
            'pad.bs': '退格（长按清空）',
            'pad.bs.aria': '退格，长按清空输入框',
            'pad.send': '发送',
            'pad.quick.aria': '电脑快捷控制',
            'pad.esc': 'ESC 退出键',
            'pad.vol.down': '音量减',
            'pad.vol.up': '音量加',
            'pad.media.aria': '打开网站（长按编辑）',
            'pad.media.title': '单击打开网站 · 长按编辑',
            'pad.gyro.left': '左键',
            'pad.gyro.right': '右键',
            'pad.gyro.left.aria': '鼠标左键',
            'pad.gyro.right.aria': '鼠标右键',
            'pad.wheel.up': '长按连续上滚',
            'pad.wheel.down': '长按连续下滚',
            'pad.vl.listening': '正在聆听…',
            'pad.vl.ph': '说完松手，整段文字会打到电脑光标处',
            'pad.modes': '控制模式',
            'pad.mode.pad': '触摸板',
            'pad.mode.gyro': '陀螺仪',
            'pad.voice.title': '按住说话（轻点唤起键盘）',
            'pad.voice.aria': '按住说话',
            'pad.sheet.title': '媒体键网址',
            'pad.sheet.sub': '单击媒体键在电脑上打开，长按可随时改',
            'pad.sheet.reset': '恢复默认',
            'pad.toast.opened': '已在电脑打开',
            'pad.toast.openfail': '打开失败',
            'pad.toast.badurl': '网址不合法',
            'pad.toast.resetdone': '已恢复默认',
            'pad.toast.connecting': '正在连接…',
            'pad.toast.nopc': '连不上电脑',
            'pad.mic.perm': '没拿到麦克风权限',
            'pad.mic.unavailable': '麦克风不可用',
            'pad.mic.hint': '去「设置 → 应用 → Movo → 权限」里允许麦克风',
            'pad.mic.nodata': '没收到声音数据',
            'pad.stt.loading': '识别引擎还在加载，稍等一下',
            'pad.stt.loading.short': '识别引擎加载中，约 5 秒',
            'pad.stt.recognizing': '识别中…',
            'pad.stt.done': '已上屏',
            'pad.stt.miss': '没听清，再说一次',

            /* ---------- 键盘页 ---------- */
            'kb.vol.down': '音量−',
            'kb.vol.up': '音量+',
            'kb.vol.down.aria': '音量减',
            'kb.vol.up.aria': '音量加',
            'kb.mute': '静音',
            'kb.terminal': '终端',
            'kb.terminal.aria': '打开终端',
            'kb.shutdown': '关机',
            'kb.shutdown.aria': '长按关机',
            'kb.shutdown.hold': '长按 1 秒关机',
            'kb.fkeys': '电脑功能键',
            'kb.toast.terminal': '已打开终端',
            'kb.toast.shutdown': '电脑即将关机',
            'kb.toast.holdshutdown': '长按 1 秒关机',

            /* ---------- Code 页 ---------- */
            'cp.brand': 'Code 遥控器',
            'cp.brand.sub': '给 AI 编程助手当键盘',
            'cp.grp.chat': 'AI 对话',
            'cp.send': '发送 / 确认',
            'cp.stop': '停止生成 / 关闭',
            'cp.ctrlenter': '发送并保留',
            'cp.tab': '接受补全',
            'cp.bs': '退格',
            'cp.grp.nav': '导航（方向键可长按连发）',
            'cp.grp.edit': '编辑',
            'cp.save': '保存',
            'cp.undo': '撤销',
            'cp.redo': '重做',
            'cp.comment': '整行注释',
            'cp.paste': '粘贴',
            'cp.find': '查找',
            'cp.grp.win': '窗口与文件',
            'cp.grp.voice': '语音输入（按住说话 · 松手整段上屏）',
            'cp.voice.hold': '按住说话',
            'cp.switch': '切窗口',
            'cp.nexttab': '切标签',
            'cp.closetab': '关标签',
            'cp.gofile': '搜文件',
            'cp.panel': '终端面板',
            'cp.format': '格式化',
            'cp.grp.macro': '命令宏（点一下发送并回车 · 长按编辑）',
            'cp.sheet.title': '编辑命令宏',
            'cp.sheet.sub': '保存后点按钮即整条发送到电脑并自动回车；清空内容可移除该槽',
            'cp.sheet.clear': '清空',
            'cp.empty': '+ 空槽（点按编辑）',
            'cp.toast.sent': '已发送：',
            'cp.toast.cleared': '已清空',

            /* ---------- 设置页 ---------- */
            'set.title': '设置',
            'set.brandline': '随心而动，轻松掌控',
            'set.addr': '电脑服务地址',
            'set.addr.hint': 'IP:端口',
            'set.addr.ph': '192.168.31.12:5888',
            'set.pad.sense': '触控板灵敏度',
            'set.gyro.sense': '空鼠（陀螺仪）灵敏度',
            'set.type.delay': '输入停顿后自动发送',
            'set.sec': '秒',
            'set.hand': '操作手',
            'set.hand.hint': '滚轮条放哪边',
            'set.hand.left': '左手',
            'set.hand.right': '右手',
            'set.display': '显示模式',
            'set.display.hint': '状态栏和导航栏',
            'set.display.on': '显示系统栏',
            'set.display.off': '全屏沉浸',
            'set.theme': '主题',
            'set.theme.hint': '所有页面统一生效',
            'set.theme.dark': '夜间',
            'set.theme.light': '日间',
            'set.lang': '语言 / Language',
            'set.lang.hint': '所有页面统一生效',
            'set.ok': '确定',
            'set.connecting': '连接中…',
            'set.toast.badaddr': '地址格式不对，例如 192.168.31.12:5888',
            'set.toast.timeout': '连接超时：检查电脑服务是否在运行',
            'set.toast.connectfail': '连不上电脑：检查服务是否在运行、IP 是否正确',
            'set.toast.fs.on': '已切换到全屏沉浸',
            'set.toast.fs.off': '已显示系统栏',
            'set.toast.theme.dark': '已切换到夜间模式',
            'set.toast.theme.light': '已切换到日间模式',
            'set.toast.lang.zh': '已切换到中文',
            'set.toast.lang.en': 'Switched to English',
            'welcome.cn': '随动',
            'welcome.tag': '随心而动 · 轻松掌控',
            'set.foot': 'Movo'
        },

        en: {
            'app.title.pad': 'Movo | Touchpad',
            'app.title.kb': 'Movo | Keyboard',
            'app.title.cp': 'Movo | Code',
            'conn.offline': 'Disconnected · tap to refresh',
            'conn.sleep': 'Asleep · tap to wake',
            'conn.waking': 'Connecting…',
            'common.back': 'Back',
            'common.cancel': 'Cancel',
            'common.save': 'Save',
            'common.backhome': 'Back to home',
            'common.saved': 'Saved',

            'pad.kb': 'Keyboard mode',
            'pad.settings': 'Settings',
            'pad.ph': 'Type or speak — sends when you pause',
            'pad.bs': 'Backspace (hold to clear)',
            'pad.bs.aria': 'Backspace, hold to clear the input',
            'pad.send': 'Send',
            'pad.quick.aria': 'PC shortcuts',
            'pad.esc': 'ESC key',
            'pad.vol.down': 'Volume down',
            'pad.vol.up': 'Volume up',
            'pad.media.aria': 'Open site (hold to edit)',
            'pad.media.title': 'Tap to open · hold to edit',
            'pad.gyro.left': 'Left',
            'pad.gyro.right': 'Right',
            'pad.gyro.left.aria': 'Left click',
            'pad.gyro.right.aria': 'Right click',
            'pad.wheel.up': 'Hold to scroll up',
            'pad.wheel.down': 'Hold to scroll down',
            'pad.vl.listening': 'Listening…',
            'pad.vl.ph': 'Release when done — the text goes to your PC cursor',
            'pad.modes': 'Control mode',
            'pad.mode.pad': 'Touchpad',
            'pad.mode.gyro': 'Gyro',
            'pad.voice.title': 'Hold to talk (tap for keyboard)',
            'pad.voice.aria': 'Hold to talk',
            'pad.sheet.title': 'Media key URL',
            'pad.sheet.sub': 'Tap the media key to open it on your PC; hold to edit',
            'pad.sheet.reset': 'Reset',
            'pad.toast.opened': 'Opened on your PC',
            'pad.toast.openfail': 'Failed to open',
            'pad.toast.badurl': 'Invalid URL',
            'pad.toast.resetdone': 'Reset to default',
            'pad.toast.connecting': 'Connecting…',
            'pad.toast.nopc': 'Can\'t reach your PC',
            'pad.mic.perm': 'Microphone permission denied',
            'pad.mic.unavailable': 'Microphone unavailable',
            'pad.mic.hint': 'Allow the microphone in Settings → Apps → Movo → Permissions',
            'pad.mic.nodata': 'No audio received',
            'pad.stt.loading': 'Speech engine is still loading, one moment',
            'pad.stt.loading.short': 'Speech engine loading, about 5s',
            'pad.stt.recognizing': 'Recognizing…',
            'pad.stt.done': 'Typed',
            'pad.stt.miss': 'Didn\'t catch that, say it again',

            'kb.vol.down': 'Vol −',
            'kb.vol.up': 'Vol +',
            'kb.vol.down.aria': 'Volume down',
            'kb.vol.up.aria': 'Volume up',
            'kb.mute': 'Mute',
            'kb.terminal': 'Terminal',
            'kb.terminal.aria': 'Open terminal',
            'kb.shutdown': 'Power off',
            'kb.shutdown.aria': 'Hold to power off',
            'kb.shutdown.hold': 'Hold 1s to power off',
            'kb.fkeys': 'PC function keys',
            'kb.toast.terminal': 'Terminal opened',
            'kb.toast.shutdown': 'Your PC is shutting down',
            'kb.toast.holdshutdown': 'Hold for 1 second to power off',

            'cp.brand': 'Code Remote',
            'cp.brand.sub': 'A keypad for your AI coding assistant',
            'cp.grp.chat': 'AI chat',
            'cp.send': 'Send / Enter',
            'cp.stop': 'Stop / Close',
            'cp.ctrlenter': 'Send & keep',
            'cp.tab': 'Accept completion',
            'cp.bs': 'Backspace',
            'cp.grp.nav': 'Navigation (hold arrows to repeat)',
            'cp.grp.edit': 'Edit',
            'cp.save': 'Save',
            'cp.undo': 'Undo',
            'cp.redo': 'Redo',
            'cp.comment': 'Toggle comment',
            'cp.paste': 'Paste',
            'cp.find': 'Find',
            'cp.grp.win': 'Windows & files',
            'cp.grp.voice': 'Voice input (hold to talk, typed on release)',
            'cp.voice.hold': 'Hold to talk',
            'cp.switch': 'Switch window',
            'cp.nexttab': 'Next tab',
            'cp.closetab': 'Close tab',
            'cp.gofile': 'Go to file',
            'cp.panel': 'Terminal panel',
            'cp.format': 'Format',
            'cp.grp.macro': 'Macros (tap to send + Enter · hold to edit)',
            'cp.sheet.title': 'Edit macro',
            'cp.sheet.sub': 'Saved macros are sent to your PC with Enter; clear the text to remove a slot',
            'cp.sheet.clear': 'Clear',
            'cp.empty': '+ Empty slot (tap to edit)',
            'cp.toast.sent': 'Sent: ',
            'cp.toast.cleared': 'Cleared',

            'set.title': 'Settings',
            'set.brandline': 'Move at will, stay in control',
            'set.addr': 'PC address',
            'set.addr.hint': 'IP:port',
            'set.addr.ph': '192.168.31.12:5888',
            'set.pad.sense': 'Touchpad sensitivity',
            'set.gyro.sense': 'Air mouse (gyro) sensitivity',
            'set.type.delay': 'Auto-send after typing pause',
            'set.sec': 's',
            'set.hand': 'Hand',
            'set.hand.hint': 'Which side the wheel sits',
            'set.hand.left': 'Left',
            'set.hand.right': 'Right',
            'set.display': 'Display',
            'set.display.hint': 'Status and navigation bars',
            'set.display.on': 'Show bars',
            'set.display.off': 'Fullscreen',
            'set.theme': 'Theme',
            'set.theme.hint': 'Applies to all pages',
            'set.theme.dark': 'Dark',
            'set.theme.light': 'Light',
            'set.lang': 'Language',
            'set.lang.hint': 'Applies to all pages',
            'set.ok': 'OK',
            'set.connecting': 'Connecting…',
            'set.toast.badaddr': 'Invalid address, e.g. 192.168.31.12:5888',
            'set.toast.timeout': 'Connection timed out: is the PC service running?',
            'set.toast.connectfail': 'Can\'t reach your PC: check the service and the IP',
            'set.toast.fs.on': 'Switched to fullscreen',
            'set.toast.fs.off': 'System bars shown',
            'set.toast.theme.dark': 'Switched to dark mode',
            'set.toast.theme.light': 'Switched to light mode',
            'set.toast.lang.zh': '已切换到中文',
            'set.toast.lang.en': 'Switched to English',
            'welcome.cn': '',
            'welcome.tag': 'Move at will · stay in control',
            'set.foot': 'Movo'
        }
    };

    var cur = null;

    function readLang() {
        var v = null;
        try {
            var q = new URLSearchParams(location.search).get('lang');
            if (q === 'zh' || q === 'en') v = q;
        } catch (e) { }
        if (!v) {
            try {
                if (window.MovoNative && MovoNative.getPref) v = MovoNative.getPref('ui_lang');
            } catch (e) { }
        }
        if (v !== 'zh' && v !== 'en') {
            try { v = localStorage.getItem('movo_lang'); } catch (e) { }
        }
        return (v === 'en') ? 'en' : 'zh';
    }

    function t(key, a, b) {
        var d = D[lang()] || D.zh;
        var s = d[key];
        if (s === undefined || s === null) s = D.zh[key];
        if (s === undefined || s === null) return key;
        if (a !== undefined) s = String(s).replace('{0}', a);
        if (b !== undefined) s = String(s).replace('{1}', b);
        return s;
    }

    function lang() {
        if (!cur) cur = readLang();
        return cur;
    }

    function apply(root) {
        var r = root || document;
        r.querySelectorAll('[data-i18n]').forEach(function (el) {
            var s = t(el.getAttribute('data-i18n'));
            if (s !== '') el.textContent = s;
        });
        r.querySelectorAll('[data-i18n-ph]').forEach(function (el) {
            el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph')));
        });
        r.querySelectorAll('[data-i18n-title]').forEach(function (el) {
            el.setAttribute('title', t(el.getAttribute('data-i18n-title')));
        });
        r.querySelectorAll('[data-i18n-aria]').forEach(function (el) {
            el.setAttribute('aria-label', t(el.getAttribute('data-i18n-aria')));
        });
        document.documentElement.setAttribute('lang', lang() === 'en' ? 'en' : 'zh-CN');
        document.documentElement.setAttribute('data-lang', lang());
    }

    function set(l) {
        cur = (l === 'en') ? 'en' : 'zh';
        try { localStorage.setItem('movo_lang', cur); } catch (e) { }
        try {
            if (window.MovoNative && MovoNative.setPref) MovoNative.setPref('ui_lang', cur);
        } catch (e) { }
        apply();
    }

    window.MovoLang = { t: t, apply: apply, set: set, lang: lang, dict: D };

    // 首绘前先把 lang / data-lang 定下来，CSS 里可以按语言做微调
    try {
        document.documentElement.setAttribute('lang', lang() === 'en' ? 'en' : 'zh-CN');
        document.documentElement.setAttribute('data-lang', lang());
    } catch (e) { }
})();
