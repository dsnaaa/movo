"""一次性把可能卡在按下状态的鼠标键全部释放。

用于手机端 touchend 丢失（切后台、页面重载、App 被杀）后，电脑上的
左键 / 中键一直处在“被按住”状态：
  - 左键按住 → 点哪里都变成拖选，看起来像“鼠标失灵”
  - 中键按住 → Windows 会直接吞掉左右键点击

用法：.venv\\Scripts\\python.exe release_mouse.py
"""
import ctypes
import sys
import time

from pynput.mouse import Controller, Button

mouse = Controller()

_VK = {Button.left: 0x01, Button.right: 0x02, Button.middle: 0x04}

user32 = ctypes.windll.user32 if sys.platform == 'win32' else None


def is_down(btn):
    if user32 is None:
        return True
    return bool(user32.GetAsyncKeyState(_VK[btn]) & 0x8000)


# 只松真的按着的键：没按着还去 release，会凭空给前台窗口发一个 UP 事件，
# 窗口收到 WM_RBUTTONUP 就直接弹右键菜单 —— 急救脚本自己变成"鬼"就尴尬了。
for btn in (Button.left, Button.middle, Button.right):
    if not is_down(btn):
        print(f'{btn.name}: not pressed, skip')
        continue
    try:
        mouse.release(btn)
        print(f'{btn.name}: released')
    except Exception as e:
        print('release failed:', btn, e)

time.sleep(0.2)

if user32 is not None:
    state = {
        'LEFT': user32.GetAsyncKeyState(0x01) & 0x8000,
        'MIDDLE': user32.GetAsyncKeyState(0x04) & 0x8000,
        'RIGHT': user32.GetAsyncKeyState(0x02) & 0x8000,
    }
    for name, down in state.items():
        print(f'{name}: {"STILL DOWN" if down else "released"}')
    if any(state.values()):
        sys.exit(1)
else:
    print('released left / middle / right')
