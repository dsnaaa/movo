/**
 * Touchpad Module for Movo (随动)
 * Encapsulates movement, scrolling, multi-touch gestures, and long-press dragging.
 */
class Touchpad {
    constructor(elementId, socket, options = {}) {
        this.pad = document.getElementById(elementId);
        if (!this.pad) return;

        this.socket = socket;
        this.getSensitivity = options.getSensitivity || (() => 4.0);
        this.feedback = options.feedback || (() => { });

        this.lx = 0; this.ly = 0; // last x, y
        this.sx = 0; this.sy = 0; // start x, y
        this.hMove = false;
        this.tCount = 0;
        this.maxTCount = 0;
        this.drag = false;
        this.longPressTimer = null;
        this.lastMultiTouchTime = 0;
        this.pendX = 0; this.pendY = 0;  // 攒到下一帧的位移
        this.moveRaf = 0;
        this.gStart = 0;        // 本次手势的起始时刻
        this.muteUntil = 0;     // 页面刚恢复时的一小段静默期

        /* 双指捏合缩放（= Ctrl + 滚）：和滚动共用两根手指，
           靠「两指间距」判方向——间距明显变了就是捏合，否则还是滚动。 */
        this.PINCH_ENTRY = 30;  // 间距变化超过 30px 才认定是捏合（小了容易把滚动误判成缩放）
        this.PINCH_STEP = 26;   // 之后每变 26px 缩一档（太小会一点就放大过头）
        this.pinch = false;     // 本次手势已锁定为缩放，松手前不再滚动
        this.pinchRef = 0;      // 上次采样时的两指间距
        this.pinchAcc = 0;      // 攒够一档就发一次
        this.midY = null;       // 双指中点的上次纵坐标（滚动用）

        this._bindEvents();
    }

    _bindEvents() {
        this.pad.oncontextmenu = (e) => e.preventDefault();

        this.pad.addEventListener('touchstart', e => this._handleTouchStart(e));
        this.pad.addEventListener('touchmove', e => this._handleTouchMove(e), { passive: false });
        this.pad.addEventListener('touchend', e => this._handleTouchEnd(e));
        this.pad.addEventListener('touchcancel', () => this._handleTouchCancel());
    }

    /** 诊断上报（页面提供 window.diag 时生效，没有就静默） */
    _d(msg) {
        try {
            if (window.diag) window.diag('[pad] ' + msg);
        } catch (e) { }
    }

    /** 只统计真正落在触控板矩形内的触点，返回 {n, outside, list}
     *  有些 WebView 的 targetTouches 会把屏幕上的所有触点都带上，
     *  于是“一根手指点顶栏按钮 + 另一根搭在触控板上”会被数成两指 → 莫名右键。
     *  这里按坐标硬过滤：落在板外的触点既不算数，也会让整次手势作废（不触发任何点击）。 */
    _hit(e) {
        const list = e.targetTouches || e.touches || [];
        let r = null;
        try { r = this.pad.getBoundingClientRect(); } catch (err) { }
        if (!r) return { n: list.length, outside: 0, list: Array.from(list) };
        const inside = [];
        let outside = 0;
        for (let i = 0; i < list.length; i++) {
            const t = list[i];
            if (t.clientX >= r.left && t.clientX <= r.right &&
                t.clientY >= r.top && t.clientY <= r.bottom) inside.push(t);
            else outside++;
        }
        return { n: inside.length, outside, list: inside };
    }

    _handleTouchStart(e) {
        const hit = this._hit(e);
        const n = hit.n;
        const wasIdle = this.tCount === 0 || !this.gStart;   // 上一轮已经收尾
        const tgt = e.target;
        const desc = tgt ? (tgt.id || (typeof tgt.className === 'string' ? tgt.className : '') || tgt.tagName) : '?';
        this._d('start n=' + n + ' out=' + hit.outside + ' idle=' + (wasIdle ? 1 : 0) + ' target=' + desc);
        this.tCount = n;

        /* 只有“从零开始”的落指才算一次新手势。
           切 App、跳页面、从 bfcache 恢复时 touchend 可能收不到，上一次手势留下的
           maxTCount 就会残留 —— 那样接下来一次单指点按会被当成双指，凭空点出一个右键。
           所以这里一律以“本次真的同时按下了几根手指”为准，落单指时强制归位。 */
        if (n <= 1) {
            this.maxTCount = Math.max(1, n);
            this.hMove = false;
            this.gStart = Date.now();
            this.outside = hit.outside > 0;   // 新手势：重新记账是否有手指在板外
        } else if (wasIdle) {
            this.maxTCount = n;              // 双指/三指也是从零开始
            this.hMove = false;
            this.gStart = Date.now();
            this.outside = hit.outside > 0;
            if (n >= 2) this._resetPinch(); // 新手势重新量两指间距
        } else {
            this.maxTCount = Math.max(this.maxTCount || 1, n);
            if (hit.outside) this.outside = true;
        }
        if (!n) return;   // 触点全在板外，本次不参与任何手势

        const touch = hit.list[0];
        this.lx = touch.clientX;
        this.ly = touch.clientY;
        this.sx = this.lx;
        this.sy = this.ly;

        // Long press for drag (single finger)
        if (this.tCount === 1) {
            this.longPressTimer = setTimeout(() => {
                if (this.outside) return;   // 这根手指多半不是想操作触控板
                this.drag = true;
                this.socket.emit('drag_start');
                this.pad.classList.add('dragging');
                this.feedback('long');
            }, 500);
        }

        // Three finger visual feedback (drag starts on move)
        if (this.tCount === 3) {
            this.pad.classList.add('dragging');
        }
    }

    _handleTouchMove(e) {
        e.preventDefault();
        const prevTCount = this.tCount;
        const hit = this._hit(e);
        this.tCount = hit.n;
        if (hit.outside) this.outside = true;
        this.maxTCount = Math.max(this.maxTCount || 1, this.tCount);
        if (!hit.n) return;   // 板内已经没有手指了（可能是别的区域在动）

        const touch = hit.list[0];
        const cx = touch.clientX, cy = touch.clientY;

        // Multi-touch to single-touch lock (300ms)
        if (prevTCount >= 2 && this.tCount === 1) {
            this.lastMultiTouchTime = Date.now();
        }

        // Movement threshold
        if (Math.hypot(cx - this.sx, cy - this.sy) > 5) {
            this.hMove = true;
            if (this.longPressTimer) {
                clearTimeout(this.longPressTimer);
                this.longPressTimer = null;
            }
            // Three finger drag start
            if (this.tCount === 3 && !this.drag) {
                this.drag = true;
                this.socket.emit('drag_start');
            }
        }

        const sensitivity = this.getSensitivity();

        if (this.tCount === 1 || this.tCount === 3) {
            if (Date.now() - this.lastMultiTouchTime > 300) {
                // 先攒着，下一帧统一发一次。高刷屏（120Hz 以上）触控采样更高，
                // 每个 touchmove 都 emit 会让 socket 被撑满、光标反而更抖。
                this.pendX += (cx - this.lx) * sensitivity;
                this.pendY += (cy - this.ly) * sensitivity;
                this._flushMove();
            }
            this.lx = cx;
            this.ly = cy;
        } else if (this.tCount === 2) {
            // 滚动/缩放时持续更新lastMultiTouchTime, 确保松手后300ms内不移动鼠标
            this.lastMultiTouchTime = Date.now();

            /* 两根手指都抓到了才谈得上捏合；只剩一根在板内（另一根搭在板外）
               就退回老的单点滚动，不然手势会突然失效。 */
            if (hit.list.length < 2) {
                const dyFallback = cy - this.ly;
                if (Math.abs(dyFallback) > 5) {
                    this.socket.emit('scroll', { dy: dyFallback > 0 ? 1 : -1 });
                    this.feedback('scroll');
                    this.ly = cy;
                }
                return;
            }

            const a = hit.list[0], b = hit.list[1];
            const dist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
            const midY = (a.clientY + b.clientY) / 2;

            if (!this.pinchRef) this.pinchRef = dist;
            if (this.midY === null) this.midY = midY;

            /* 一旦间距变化超过阈值，这次手势就锁定为缩放：
               否则放大到一半松一下手指，页面又开始滚，手感会很怪。 */
            if (!this.pinch && Math.abs(dist - this.pinchRef) > this.PINCH_ENTRY) {
                this.pinch = true;
                this.pinchRef = dist;
                this.pinchAcc = 0;
                this.pad.classList.add('pinching');
                this.feedback('scroll');
            }

            if (this.pinch) {
                this.pinchAcc += dist - this.pinchRef;
                this.pinchRef = dist;
                let n = 0;
                while (this.pinchAcc >= this.PINCH_STEP) { n++; this.pinchAcc -= this.PINCH_STEP; }
                while (this.pinchAcc <= -this.PINCH_STEP) { n--; this.pinchAcc += this.PINCH_STEP; }
                if (n) {
                    // 两指张开（间距变大）= 放大
                    this.socket.emit('zoom', { dir: n > 0 ? 1 : -1, steps: Math.abs(n) });
                    this.feedback('scroll');
                }
                return;   // 缩放中不滚动
            }

            // 还没进入捏合：照旧按两指中点的纵向位移滚动
            if (Math.abs(midY - this.midY) > 5) {
                this.socket.emit('scroll', { dy: midY > this.midY ? 1 : -1 });
                this.feedback('scroll');
                this.midY = midY;
            }
        }
    }

    _flushMove() {
        if (this.moveRaf) return;
        this.moveRaf = requestAnimationFrame(() => {
            this.moveRaf = 0;
            const dx = this.pendX;
            const dy = this.pendY;
            this.pendX = 0;
            this.pendY = 0;
            if (dx || dy) this.socket.emit('move', { dx, dy });
        });
    }

    /** 点按位置的涟漪反馈（strong = 右键，圈更大） */
    _tapFlash(strong) {
        const pad = this.pad;
        if (!pad) return;
        const r = pad.getBoundingClientRect();
        const f = document.createElement('span');
        f.className = 'tapflash';
        f.style.left = (this.lx - r.left) + 'px';
        f.style.top = (this.ly - r.top) + 'px';
        if (strong) { f.style.width = '64px'; f.style.height = '64px'; }
        pad.appendChild(f);
        setTimeout(() => { if (f.parentNode) f.remove(); }, 380);
    }

    _handleTouchEnd(e) {
        const prevTCount = this.tCount;
        const hit = this._hit(e);
        const n = hit.n;                                    // 板内还剩几根手指
        const globalLeft = e.touches ? e.touches.length : 0; // 屏幕上还有几根手指
        if (hit.outside) this.outside = true;
        this.tCount = n;

        if (prevTCount >= 2 && n === 1) {
            this.lastMultiTouchTime = Date.now();
        }

        if (this.longPressTimer) {
            clearTimeout(this.longPressTimer);
            this.longPressTimer = null;
        }

        if (this.drag) {
            if (n === 0 && globalLeft === 0) {
                this.socket.emit('drag_end');
                this.drag = false;
            }
            if (n === 0) this._endGesture();
            return;   // 拖拽结束不判点击
        }

        if (n > 0 && globalLeft > 0) return;   // 板内还有手指，等最后一根

        /* 点按判定：只有“手指确实同时按过几根”+“没移动”+“够快”+“没碰到板外”才算数。
           页面刚从后台/别的页面回来时有一小段静默期（muteUntil），
           避免恢复瞬间的手势尾巴打出一个莫名其妙的点击。 */
        const dur = Date.now() - (this.gStart || 0);
        const muted = Date.now() < (this.muteUntil || 0);
        this._d('end max=' + this.maxTCount + ' dur=' + dur + ' moved=' + (this.hMove ? 1 : 0)
            + ' muted=' + (muted ? 1 : 0) + ' out=' + (this.outside ? 1 : 0));
        if (!this.outside && !this.hMove && !muted && dur < 600) {
            // 三指 / 双指 / 单指：震动等级各不相同，让人闭眼也能分清点了哪个键
            if (this.maxTCount === 1) {
                this.socket.emit('click', { button: 'left' });
                this.feedback('tap');
                this._tapFlash();
            } else if (this.maxTCount === 2) {
                this.socket.emit('click', { button: 'right' });
                this.feedback('right');
                this._tapFlash(true);
            } else if (this.maxTCount >= 3) {
                this.socket.emit('click', { button: 'middle' });
                this.feedback('tap');
                this._tapFlash();
            }
        }

        this._endGesture();
    }

    /** 手势收尾：状态全部归零，不涉及任何 socket 事件 */
    _endGesture() {
        this.tCount = 0;
        this.maxTCount = 0;
        this.gStart = 0;
        this.hMove = false;
        if (this.longPressTimer) {
            clearTimeout(this.longPressTimer);
            this.longPressTimer = null;
        }
        if (this.pad) this.pad.classList.remove('dragging');
        this._resetPinch();
        if (window.stopScroll) window.stopScroll();
    }

    /** 捏合状态归零（手势开始/结束都调） */
    _resetPinch() {
        this.pinch = false;
        this.pinchRef = 0;
        this.pinchAcc = 0;
        this.midY = null;
        if (this.pad) this.pad.classList.remove('pinching');
    }

    /** 供页面生命周期调用：切 App / 返回 / 从缓存恢复时把手势状态清零。
     *  mute=true 时顺带静默 250ms，挡掉恢复瞬间的手势尾巴。 */
    reset(mute) {
        this._endGesture();
        this.drag = false;
        this.lastMultiTouchTime = 0;
        this.pendX = 0;
        this.pendY = 0;
        // mute 传数字 = 静音这么多毫秒（唤醒时用）；false = 不静音；其它 = 默认 250ms
        this.muteUntil = typeof mute === 'number'
            ? Date.now() + mute
            : (mute === false ? 0 : Date.now() + 250);
    }

    _handleTouchCancel() {
        this._endGesture();
        if (this.drag) {
            this.socket.emit('drag_end');
            this.drag = false;
        }
    }

    // External access to current multitouch lock
    isLocked() {
        return (Date.now() - this.lastMultiTouchTime < 300);
    }

    getLastMultiTouchTime() {
        return this.lastMultiTouchTime;
    }
}

// Export for use in scripts
window.TouchpadModule = Touchpad;
