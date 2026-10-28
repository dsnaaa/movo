/* ============================================================
 * MovoVoice —— 「按住说话」语音输入（触控板页 / Code 页共用）
 *
 * 手机只做两件事：把声音按 16kHz 单声道 PCM 每 100ms 一包发出去、
 * 把回传的文字实时显示在浮层里。识别在电脑端完成（火山豆包为主，
 * 本地 SenseVoice 兜底），所以手机不装模型、也不放 API Key 进 APK。
 *
 * 上屏策略（用户拍板，勿改）：说话中只显示、不打字；松手后整段
 * type_text 打到电脑光标处，避免半句话被反复改写。
 *
 * 用法：
 *   MovoVoice.attach({
 *     socket, link, t, toast, haptic,
 *     btnId:'voice-btn', layerId:'voice-layer', headId:'vl-head',
 *     labelId:'vl-label', textId:'vl-text',
 *     onStart(){}, onEnd(){}, onTap(){}, onTyped(){}
 *   });
 * ============================================================ */
(function () {
    'use strict';

    function noop() { }

    function attach(o) {
        o = o || {};
        var socket = o.socket;
        if (!socket) throw new Error('MovoVoice: socket required');

        var link = o.link || {};
        var T = o.t || function (k) { return k; };
        var toast = o.toast || noop;
        var haptic = o.haptic || noop;
        var onStart = o.onStart || noop;
        var onEnd = o.onEnd || noop;
        var onTap = o.onTap || null;
        var onTyped = o.onTyped || noop;
        var aboveBtn = !!o.aboveBtn;     // 浮层挂在按钮上方（页内可滚动、底部按钮的页面用）

        var btn = document.getElementById(o.btnId || 'voice-btn');
        var layer = document.getElementById(o.layerId || 'voice-layer');
        var head = document.getElementById(o.headId || 'vl-head');
        var label = document.getElementById(o.labelId || 'vl-label');
        var text = document.getElementById(o.textId || 'vl-text');
        if (!btn || !layer || !head || !label || !text) return null;

        var V_BUILD = o.build || 'b1028-1538';   // 构建标记：出问题一眼看出手机上跑的是哪一版
        var V_CHUNK = 1600;      // 100ms @16kHz，和服务端一致
        var V_TAP_MS = 320;      // 短于这个时长且没识别到字 → 当「轻点」

        var ready = false;       // 电脑端识别引擎是否就绪
        var hint = '';           // 引擎没就绪时给用户看的原因
        var holding = false;     // 手指是否还按在按钮上
        var recording = false;
        var finishing = false;   // 已松手，等电脑回最终文本
        var discard = false;     // 本次录音作废（轻点）
        var gotText = false;
        var startedAt = 0;
        var test = false;        // ?vtest=N 调试钩子：自动按住 N 秒且不往电脑打字

        var ctx = null, stream = null, src = null, proc = null;
        var pending = new Int16Array(0);
        var finTimer = null, waitTimer = null;
        var nativeBytes = 0, nativeWatch = null;

        function labelSet(txt, done) {
            label.textContent = txt;
            head.classList.toggle('done', !!done);
        }

        /* ---- 贴按钮上方：把浮层抬到话筒按钮的上边缘之上，手指按着也能看全。
           页面不移动、不垫空白，浮层盖住下面的内容没关系（就是这么设计的）。 ---- */
        var placeRaf = null;

        function place() {
            if (!aboveBtn) return;
            var r = btn.getBoundingClientRect();
            var vh = window.innerHeight || document.documentElement.clientHeight;
            var bottom = Math.max(10, vh - r.top + 10);      // 按钮上边缘再往上 10px
            var maxBottom = vh - layer.offsetHeight - 8;     // 别顶出屏幕
            if (bottom > maxBottom) bottom = Math.max(10, maxBottom);
            layer.style.bottom = Math.round(bottom) + 'px';
        }

        function schedulePlace() {
            if (!aboveBtn) return;
            if (placeRaf) cancelAnimationFrame(placeRaf);
            placeRaf = requestAnimationFrame(function () { placeRaf = null; place(); });
        }

        function open() {
            text.textContent = T('pad.vl.ph');
            text.classList.add('placeholder');
            labelSet(T('pad.vl.listening'));
            layer.classList.add('show');
            if (aboveBtn) {
                place();               // 先摆到位，再让过渡动画把它从下方淡入
                window.addEventListener('resize', schedulePlace);
            }
        }

        function close() {
            layer.classList.remove('show');
            btn.classList.remove('rec');
            if (aboveBtn) window.removeEventListener('resize', schedulePlace);
        }

        function show(txt) {
            if (!txt) return;
            gotText = true;
            text.classList.remove('placeholder');
            text.textContent = txt;
            schedulePlace();
            text.scrollTop = text.scrollHeight;   // 长了就跟着往下滚
        }

        function toInt16(f32, inRate) {
            var samples = f32;
            if (inRate !== 16000) {
                // 设备不给 16k 时线性插值重采样，够语音用
                var ratio = inRate / 16000;
                var len = Math.floor(f32.length / ratio);
                samples = new Float32Array(len);
                for (var i = 0; i < len; i++) {
                    var pos = i * ratio;
                    var i0 = Math.floor(pos);
                    var i1 = Math.min(i0 + 1, f32.length - 1);
                    var frac = pos - i0;
                    samples[i] = f32[i0] * (1 - frac) + f32[i1] * frac;
                }
            }
            var out = new Int16Array(samples.length);
            for (var j = 0; j < samples.length; j++) {
                var x = Math.max(-1, Math.min(1, samples[j]));
                out[j] = x < 0 ? x * 32768 : x * 32767;
            }
            return out;
        }

        function append(i16) {
            var merged = new Int16Array(pending.length + i16.length);
            merged.set(pending, 0);
            merged.set(i16, pending.length);
            pending = merged;
            while (pending.length >= V_CHUNK) {
                var chunk = pending.slice(0, V_CHUNK);
                pending = pending.slice(V_CHUNK);
                socket.emit('voice_audio', chunk.buffer);
            }
        }

        // ---- 原生录音兜底 ----
        // WebView 的 getUserMedia 在部分机型/自签证书环境下拿不到流，
        // 这时退回 App 里的 Android AudioRecord：16k 单声道，每 100ms 一包 base64 推上来，
        // 页面解码成 Int16 塞进同一条 voice_audio 通道，服务端完全不用改。
        function nativeMic() {
            try { return (window.MovoNative && MovoNative.startMic) ? window.MovoNative : null; } catch (e) { return null; }
        }

        window.__nativePcm = function (b64) {
            if (!recording) return;
            nativeBytes += b64.length;
            if (link.touch) link.touch();
            try {
                var bin = atob(b64);
                var n = bin.length >> 1;
                var out = new Int16Array(n);
                for (var i = 0; i < n; i++) {
                    var lo = bin.charCodeAt(i * 2), hi = bin.charCodeAt(i * 2 + 1);
                    var v = (hi << 8) | lo;
                    out[i] = v >= 0x8000 ? v - 0x10000 : v;
                }
                append(out);
            } catch (e) { }
        };

        /** 用原生 AudioRecord 开始采音：成功返回 'ok'，失败返回阶段码 */
        function startNativeMic() {
            var nat = nativeMic();
            if (!nat) return 'no-bridge';
            var r;
            try {
                r = nat.startMic();
            } catch (e) {
                return 'throw:' + ((e && e.message) || e);
            }
            if (r !== 'ok' && r !== true && r !== 'true') return String(r);
            pending = new Int16Array(0);
            recording = true;
            nativeBytes = 0;
            clearTimeout(nativeWatch);
            // 原生说启动了，但一包 PCM 都没上来（桥断了 / 页面收不到回调）也要能看出来
            nativeWatch = setTimeout(function () {
                if (recording && nativeBytes === 0) {
                    if (window.diag) window.diag('[mic] 原生已启动但 1.2s 内没有 PCM ' + V_BUILD);
                    labelSet(T('pad.mic.nodata') + ' ' + V_BUILD, false);
                }
            }, 1200);
            if (window.diag) window.diag('[mic] 原生录音启动 ok ' + V_BUILD);
            socket.emit('voice_start');
            return 'ok';
        }

        function teardown() {
            recording = false;
            clearTimeout(nativeWatch);
            nativeWatch = null;
            try { if (window.MovoNative && MovoNative.stopMic) MovoNative.stopMic(); } catch (e) { }
            try { if (proc) { proc.onaudioprocess = null; proc.disconnect(); } } catch (e) { }
            try { if (src) src.disconnect(); } catch (e) { }
            try { if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) { }
            try { if (ctx) ctx.close(); } catch (e) { }
            proc = src = stream = ctx = null;
        }

        function start() {
            if (recording || finishing) return;
            if (!holding) return;      // 等连接的那几百毫秒里手指已经松了

            if (!ready) {
                toast(hint || T('pad.stt.loading'));
                socket.emit('voice_status');
                return;
            }
            if (!socket.connected) {
                // 刚睡醒：叫醒连接，连上就自动接着录
                if (link.wake) link.wake();
                toast('正在连接电脑…');
                clearInterval(waitTimer);
                waitTimer = setInterval(function () {
                    if (!socket.connected) return;
                    clearInterval(waitTimer);
                    waitTimer = null;
                    start();
                }, 120);
                setTimeout(function () {
                    if (!waitTimer) return;
                    clearInterval(waitTimer);
                    waitTimer = null;
                    toast(T('pad.toast.nopc'));
                }, 4500);
                return;
            }

            startedAt = Date.now();
            gotText = false;
            discard = false;
            open();
            btn.classList.add('rec');
            onStart();                 // 触控板页用来暂停陀螺仪

            // 1) 先试 App 原生录音（自签证书下 WebView 拿不到 getUserMedia）
            var natRes = startNativeMic();
            if (natRes === 'ok') {
                if (!holding) {        // 启动这几十毫秒里手指已经松了
                    teardown();
                    close();
                    onEnd();
                }
                return;
            }
            if (window.diag) window.diag('[mic] 原生录音不可用 ' + natRes);

            // 2) 没有原生桥 / 原生失败 → 回退 WebView 的 getUserMedia
            var micErr = null;
            var md = navigator.mediaDevices;
            var getUM = (md && md.getUserMedia) ? md.getUserMedia.bind(md) : null;
            if (!getUM) {
                micErr = 'NoMediaDevices';
            } else {
                getUM({
                    audio: {
                        channelCount: 1,
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                }).then(function (s) {
                    stream = s;
                    beginWebAudio(natRes, micErr);
                }, function (e) {
                    // 少数 WebView 对具体约束支持不全（OverconstrainedError），退回最朴素的请求
                    if (e && (e.name === 'OverconstrainedError' || e.name === 'NotSupportedError' || e.name === 'TypeError')) {
                        return getUM({ audio: true }).then(function (s) {
                            stream = s;
                            beginWebAudio(natRes, null);
                        }, function (e2) {
                            failMic(natRes, (e2 && e2.name) || 'Error', e2);
                        });
                    }
                    failMic(natRes, (e && e.name) || 'Error', e);
                });
            }
            if (micErr) failMic(natRes, micErr, null);
        }

        function failMic(natRes, micErr, e) {
            if (window.diag) window.diag('[mic] getUserMedia 失败 ' + micErr + ' / ' + ((e && e.message) || ''));
            teardown();
            btn.classList.remove('rec');
            // 别用一闪而过的 toast：把失败原因留在浮层上，用户能截图，我也能定位
            labelSet(natRes === 'perm' ? T('pad.mic.perm') : T('pad.mic.unavailable'), false);
            text.classList.remove('placeholder');
            text.textContent = (natRes === 'perm'
                ? T('pad.mic.hint')
                : '原生 ' + natRes + ' · 网页 ' + micErr)
                + ' · ' + V_BUILD;
            setTimeout(function () {
                if (!recording && !holding) { close(); onEnd(); }
            }, 3600);
        }

        function beginWebAudio(natRes, unused) {
            if (!holding) {            // 授权弹窗还没关，手指就松了
                teardown();
                close();
                onEnd();
                return;
            }
            var AC = window.AudioContext || window.webkitAudioContext;
            ctx = new AC({ sampleRate: 16000 });
            var resuming = (ctx.state === 'suspended' && ctx.resume) ? ctx.resume() : Promise.resolve();
            resuming.catch(noop).then(function () {
                if (!holding) {
                    teardown();
                    close();
                    onEnd();
                    return;
                }
                try {
                    src = ctx.createMediaStreamSource(stream);
                    proc = ctx.createScriptProcessor(1024, 1, 1);
                } catch (e) {
                    failMic(natRes, (e && e.name) || 'AudioGraph', e);
                    return;
                }
                pending = new Int16Array(0);
                recording = true;
                proc.onaudioprocess = function (ev) {
                    if (!recording) return;
                    if (link.touch) link.touch();   // 一直按着也算「在用」，别让闲置休眠掐掉连接
                    append(toInt16(ev.inputBuffer.getChannelData(0), ctx.sampleRate));
                };
                src.connect(proc);
                proc.connect(ctx.destination);
                socket.emit('voice_start');
            });
        }

        function stop() {
            if (!recording) return;
            var tap = (Date.now() - startedAt < V_TAP_MS) && !gotText;

            teardown();
            btn.classList.remove('rec');

            if (socket.connected) {
                if (pending.length > 0) {   // 不足 100ms 的尾巴也要发
                    socket.emit('voice_audio', pending.slice(0).buffer);
                }
                socket.emit('voice_end');
            }
            pending = new Int16Array(0);

            if (tap && onTap) {
                // 轻点：触控板页用来唤起键盘
                discard = true;
                close();
                onEnd();
                onTap();
                return;
            }

            finishing = true;
            labelSet(T('pad.stt.recognizing'), true);
            clearTimeout(finTimer);
            finTimer = setTimeout(function () {   // 兜底：8 秒还没回就收层，别把浮层晾着
                finishing = false;
                close();
                onEnd();
            }, 8000);
        }

        socket.on('connect', function () {
            socket.emit('voice_status');
            // 麦克风相关环境打一份到电脑的 _diag.log：出问题时一眼看出是哪一层挡的
            try {
                var nat = window.MovoNative;
                if (window.diag) window.diag('[mic] env secure=' + window.isSecureContext +
                    ' md=' + !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) +
                    ' native=' + (nat && nat.version ? nat.version() : 'none'));
            } catch (e) { }
        });

        socket.on('voice_state', function (d) {
            if (!d) return;
            ready = !!d.ready;
            hint = d.error || (d.loading ? T('pad.stt.loading.short') : '');
        });

        socket.on('voice_partial', function (d) {
            if (!recording && !finishing) return;
            if (d && d.text) show(d.text);
        });

        socket.on('voice_final', function (d) {
            if (discard) { discard = false; return; }
            if (!finishing) return;
            finishing = false;
            clearTimeout(finTimer);

            var out = ((d && d.text) || '').trim();
            if (out) {
                show(out);
                labelSet(T('pad.stt.done'), true);
            } else {
                labelSet(T('pad.stt.miss'), false);
            }

            if (out && !test) {
                // 结尾是英文/代码就补个空格，连着说下一句不会粘在一起
                var pad = /[A-Za-z0-9.,?!;:)\]}>]$/.test(out) ? ' ' : '';
                socket.emit('type_text', { text: out + pad });
                onTyped();
            }

            setTimeout(function () {
                close();
                onEnd();
            }, out ? 620 : 380);
        });

        // 按住即录，松开结束。用 pointer capture：手指滑出按钮也不会中断，
        // 说长句子时手抖一下不至于把录音掐了。
        btn.addEventListener('pointerdown', function (e) {
            e.preventDefault();
            if (holding) return;
            holding = true;
            try { btn.setPointerCapture(e.pointerId); } catch (err) { }
            haptic('tap');
            start();
        });

        function release(e) {
            if (e && e.cancelable) e.preventDefault();
            if (!holding) return;
            holding = false;
            stop();
        }
        btn.addEventListener('pointerup', release);
        btn.addEventListener('pointercancel', release);
        btn.addEventListener('contextmenu', function (e) { e.preventDefault(); });

        // 切后台 / 锁屏 / 页面被换掉：立刻停录，别让服务端挂着半场会话
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState !== 'hidden') return;
            if (holding) { holding = false; stop(); }
        });
        window.addEventListener('pagehide', function () {
            if (holding) { holding = false; stop(); }
        });

        if (socket.connected) socket.emit('voice_status');

        /* 调试钩子：?vtest=6 → 引擎就绪后自动按住 6 秒再松开，且不往电脑打字。
           配合 Chrome 的 fake audio 参数可在无麦克风环境跑通整条链路。 */
        if (o.allowTest !== false) {
            var vt = new URLSearchParams(location.search).get('vtest');
            if (vt) {
                test = true;
                var sec = Math.max(1, parseFloat(vt) || 6);
                var tmr = setInterval(function () {
                    if (!ready || !socket.connected) return;
                    clearInterval(tmr);
                    setTimeout(function () {
                        if (!holding) { holding = true; start(); }
                        setTimeout(function () { holding = false; stop(); }, sec * 1000);
                    }, 400);
                }, 200);
            }
        }

        return {
            isReady: function () { return ready; },
            isRecording: function () { return recording; }
        };
    }

    window.MovoVoice = { attach: attach };
})();
