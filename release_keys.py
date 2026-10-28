"""一次性把可能卡在按下状态的键全部释放。
用于 pynput 注入的 keydown 没有配对 keyup、导致物理键盘行为异常（Ctrl/Shift/Enter 一直被当作按住）。
"""
import string
import time
from pynput.keyboard import Controller, Key

kb = Controller()

special = [
    Key.shift, Key.shift_l, Key.shift_r,
    Key.ctrl, Key.ctrl_l, Key.ctrl_r,
    Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr,
    Key.cmd, Key.cmd_l, Key.cmd_r,
    Key.enter, Key.backspace, Key.delete, Key.insert,
    Key.space, Key.tab, Key.esc, Key.caps_lock,
    Key.up, Key.down, Key.left, Key.right,
]

for k in special:
    try:
        kb.release(k)
    except Exception:
        pass

for ch in string.ascii_lowercase + string.digits + string.punctuation:
    try:
        kb.release(ch)
    except Exception:
        pass

time.sleep(0.05)
print("all keys released")
