import time
import threading
import platform
from pynput.keyboard import Controller as KeyController, Key, KeyCode
from config_manager import get_special_keys

keyboard = KeyController()
active_repeats = {} # {key_code: stop_event}

# 多媒体键（音量/播放）：键盘上没有可打印字符，走 Key.media_*。
# 前端 quickbar 发过来的键名 -> pynput Key，别名都收，省得前端改一次后端跟一次。
MEDIA_KEYS = {}
for _names, _attr in (
    (('volumeup', 'volume_up', 'vol_up', 'vol+'), 'media_volume_up'),
    (('volumedown', 'volume_down', 'vol_down', 'vol-'), 'media_volume_down'),
    (('volumemute', 'volume_mute', 'mute'), 'media_volume_mute'),
    (('playpause', 'play_pause'), 'media_play_pause'),
    (('next', 'media_next'), 'media_next'),
    (('prev', 'previous', 'media_previous'), 'media_previous'),
):
    _key_obj = getattr(Key, _attr, None)
    if _key_obj is not None:
        for _n in _names:
            MEDIA_KEYS[_n] = _key_obj

def repeat_key(key_obj, stop_event):
    """模拟系统自动重复按键的线程。

    注意：这个线程可能比 down/up 这一对事件活得久，甚至可能在 up 之后才被调度。
    如果那时才 press，就再也没人 release，键会永久卡在按下状态（Ctrl/Shift/Enter 卡住
    会让整个物理键盘行为错乱）。所以无论如何都要在退出时 release 一次。
    """
    try:
        if stop_event.is_set():          # up 已经先到了，根本不用按
            return
        keyboard.press(key_obj)
        if stop_event.wait(0.4): return
        while not stop_event.is_set():
            keyboard.press(key_obj)
            if stop_event.wait(0.05): break
    finally:
        try:
            keyboard.release(key_obj)
        except Exception:
            pass


def handle_tap(data):
    """点按一次（按下+松开），不启动重复线程，没有竞态。
    退格、回车这类“按一下”的操作一律走这里。"""
    key_code = str(data.get('key', '')).lower().strip()
    media = MEDIA_KEYS.get(key_code)
    if media is not None:
        # 音量/播放这类多媒体键不在 get_special_keys() 表里（pynput 没有对应字符），
        # 单独走 Key.media_* —— Windows 上 pynput 会自动带 EXTENDEDKEY 标志，
        # 系统收到即调节音量，和按键盘上的音量键完全等价。
        keyboard.press(media)
        time.sleep(0.015)
        keyboard.release(media)
        return
    target = get_special_keys().get(key_code, key_code)
    keyboard.press(target)
    time.sleep(0.015)
    keyboard.release(target)


_SAFE_RELEASE = [
    Key.shift, Key.shift_l, Key.shift_r,
    Key.ctrl, Key.ctrl_l, Key.ctrl_r,
    Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr,
    Key.cmd, Key.cmd_l, Key.cmd_r,
    Key.enter, Key.backspace, Key.delete, Key.insert,
    Key.space, Key.tab, Key.esc,
    Key.up, Key.down, Key.left, Key.right,
]


def release_all():
    """把所有可能卡在“按下”状态的键释放一遍。
    手机每次连上来时调用，相当于一次自动复位：就算之前有键卡住，重连即恢复。"""
    active_repeats.clear()
    for k in _SAFE_RELEASE:
        try:
            keyboard.release(k)
        except Exception:
            pass

def handle_key_action(data):
    """长按 / 松开。前端漏字段时不要抛 KeyError —— handler 一抛异常，
    回执就回不去，客户端会判成假连接然后反复重连（踩过这个坑）。"""
    data = data if isinstance(data, dict) else {}
    action = data.get('action')  # 'down' 或 'up'
    key_code = str(data.get('key', '')).lower().strip()
    if not key_code:
        return
    special_keys = get_special_keys()
    
    target_key = special_keys.get(key_code, key_code)

    if action == 'down':
        if key_code in active_repeats:
            return
        stop_event = threading.Event()
        active_repeats[key_code] = stop_event
        threading.Thread(target=repeat_key, args=(target_key, stop_event), daemon=True).start()
    else:
        if key_code in active_repeats:
            stop_event = active_repeats[key_code]
            stop_event.set()
            del active_repeats[key_code]
        keyboard.release(target_key)

def handle_type_text(data):
    text = data.get('text') if isinstance(data, dict) else None
    if text:
        keyboard.type(text)

def handle_combo(data):
    keys = data.get('keys') if isinstance(data, dict) else None
    if not keys: return
    
    special_keys = get_special_keys()
    is_mac = platform.system() == 'Darwin'
    
    pressed_keys = []
    try:
        # 按顺序按下所有键
        for k in keys:
            k_clean = k.lower().strip()
            target = special_keys.get(k_clean, k_clean)
            
            # macOS 修复：对于符号键，直接使用硬件虚拟键码同步位移标志
            # 这样 shift + 47 (dot) 就能被系统和浏览器（如 YouTube）正确识别为 >
            if is_mac and isinstance(target, str) and len(target) == 1:
                # 常见符号的 Mac 虚拟键码 (ANSI 布局)
                vk_map = {
                    '.': 47, ',': 43, '/': 44, ';': 41, "'": 39, 
                    '[': 33, ']': 30, '`': 50, '-': 27, '=': 24, '\\': 42
                }
                if target in vk_map:
                    target = KeyCode.from_vk(vk_map[target])
                else:
                    target = KeyCode.from_char(target)
            
            keyboard.press(target)
            pressed_keys.append(target)
            
            # macOS 下在按下 Shift 等修饰键后增加延迟，确保后续按键能识别到修饰状态
            if is_mac and target in (Key.shift, Key.shift_r, Key.ctrl, Key.ctrl_r, Key.alt, Key.alt_r, Key.cmd):
                time.sleep(0.1)
            else:
                # 维持组合键状态的时间
                delay = 0.05 if is_mac else 0.02
                time.sleep(delay)
        
        # 维持组合键状态的时间
        hold_time = 0.1 if is_mac else 0.05
        time.sleep(hold_time)
        
    finally:
        # 逆序释放所有键
        for target in reversed(pressed_keys):
            keyboard.release(target)
            if is_mac:
                time.sleep(0.01)
