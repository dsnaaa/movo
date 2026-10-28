/**
 * AirLink —— 手机端连接生命周期管理（触摸板 / 键盘 / 手柄三页共用）
 *
 * 设计取舍（2026-10-27 用户拍板）：
 *   不追求「永远在线」。闲置超过 61 秒就主动断开——省电、也省得挂着一根假连接；
 *   手指一碰屏幕立刻重连。断连从此是可预期的事，而不是随机故障。
 *
 * 为什么要主动断开：
 *   手机切后台/锁屏时 WebView 会把 JS 定时器冻结，任何「探测假连接」的方案都会失效，
 *   回来时连接早就是死的，只能干等超时。既然这样，不如反过来：不看的时候干脆不连。
 *
 * 三个状态：
 *   ok      已连接（提示条隐藏）
 *   sleep   休眠（灰条：轻触唤醒）
 *   waking  唤醒中（蓝条：连接中）
 *   down    真出错了（红条：点此刷新）
 */
(function (global) {
    'use strict';

    var IDLE_MS = 61000;          // 闲置多久休眠（用户指定 1 分 01 秒）
    var PROBE_MS = 3000;          // 心跳间隔
    var PROBE_TIMEOUT = 5000;     // 一次心跳最多等多久

    function noop() { }

    function create(ioOptions, hooks) {
        hooks = hooks || {};
        var onState = hooks.onState || noop;
        var onSleep = hooks.onSleep || noop;
        var onWake = hooks.onWake || noop;
        var idleMs = hooks.idleMs || IDLE_MS;

        var socket = global.io(ioOptions || {
            // polling 优先：WebView 里 wss 会被自签证书拦掉，写成 websocket 优先会直接连不上
            reconnection: true,
            reconnectionDelay: 400,
            reconnectionDelayMax: 2000,
            timeout: 8000
        });

        // 未连接时一律丢弃，别进 socket.io 的发送缓冲——
        // 否则重连那一刻会把休眠期间攒下的 move 一次性灌给电脑，指针会乱飞。
        var rawEmit = socket.emit.bind(socket);
        socket.emit = function () {
            if (!socket.connected) return socket;
            return rawEmit.apply(null, arguments);
        };

        var sleeping = false;
        var lastAct = Date.now();
        var lastAlive = Date.now();
        var hardTries = 0;
        var lastHard = 0;
        var probing = false;

        function report(state) {
            try { onState(state); } catch (e) { }
        }

        function markActive() {
            lastAct = Date.now();
        }

        socket.on('connect', function () {
            lastAlive = Date.now();
            hardTries = 0;
            report(sleeping ? 'sleep' : 'ok');
        });
        socket.on('disconnect', function () {
            if (!sleeping) report('down');
        });
        socket.on('connect_error', function () {
            if (!sleeping) report('down');
        });

        function sleep() {
            if (sleeping || !socket.connected) return;
            sleeping = true;
            try { onSleep(); } catch (e) { }     // 页面负责先松开按住的键
            report('sleep');
            // 留 80ms 让 drag_end / mid_up 真的发出去，再断
            setTimeout(function () {
                try { socket.disconnect(); } catch (e) { }
            }, 80);
        }

        function wake() {
            if (!sleeping) return;
            sleeping = false;
            markActive();
            report('waking');
            try { onWake(); } catch (e) { }
            try { socket.connect(); } catch (e) { }
            // 连上了 connect 事件会把状态刷成 ok；3 秒还没连上就当真的出问题了
            setTimeout(function () {
                if (!socket.connected && !sleeping) report('down');
            }, 3000);
        }

        function hardReconnect() {
            var now = Date.now();
            if (now - lastHard < 2500) return;   // 两次硬重连至少隔 2.5 秒，防抖
            lastHard = now;
            hardTries++;
            report('down');
            try { socket.disconnect(); } catch (e) { }
            // disconnect 之后立刻 connect 会和内部 closing 状态打架，隔一帧更稳
            setTimeout(function () { try { socket.connect(); } catch (e) { } }, 150);
        }

        /* ---- 任何交互都算「还在用」，同时把睡着的叫醒 ---- */
        ['pointerdown', 'touchstart', 'keydown', 'input', 'touchmove'].forEach(function (ev) {
            document.addEventListener(ev, function () {
                markActive();
                if (sleeping) wake();
            }, { capture: true, passive: true });
        });

        /* ---- 1 秒一次：闲置判定 ---- */
        setInterval(function () {
            if (sleeping) return;
            if (socket.connected && Date.now() - lastAct > idleMs) sleep();
        }, 1000);

        /* ---- 3 秒一次：心跳探活（睡着时完全不碰网络）---- */
        setInterval(function () {
            if (sleeping) return;
            if (!socket.connected) {
                if (Date.now() - lastAlive > 6000) hardReconnect();
                return;
            }
            if (probing) return;
            probing = true;
            socket.timeout(PROBE_TIMEOUT).emit('hb', {}, function (err) {
                probing = false;
                if (err) {
                    if (Date.now() - lastAlive > 15000) hardReconnect();
                } else {
                    lastAlive = Date.now();
                    hardTries = 0;
                }
            });
        }, PROBE_MS);

        /* ---- 从后台切回来：睡着就继续睡（等用户碰屏幕），没睡就查一下连接 ---- */
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState !== 'visible') return;
            if (sleeping) {
                report('sleep');
                return;
            }
            if (!socket.connected) {
                lastAlive = 0;
                hardReconnect();
            }
        });

        return {
            socket: socket,
            emit: function () {
                if (!socket.connected) return;
                socket.emit.apply(socket, arguments);
            },
            isSleeping: function () { return sleeping; },
            isConnected: function () { return socket.connected; },
            wake: wake,
            sleep: sleep,
            touch: markActive
        };
    }

    global.AirLink = { create: create };
})(window);
