"""救急：把软件亮度调回 100%。
正常情况下服务退出时会自动还原；但如果服务是被强杀的（taskkill /f、断电等），
屏幕会停在调暗的状态，跑这个脚本一键归位。
用法：.venv\\Scripts\\python.exe reset_brightness.py
"""
import system_service

system_service.restore_brightness()
print('brightness restored to 100%')
