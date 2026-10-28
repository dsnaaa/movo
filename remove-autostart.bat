@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Movo autostart remove

set "TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Movo.vbs"
if exist "%TARGET%" del /f /q "%TARGET%"
schtasks /delete /tn "MovoServer" /f >nul 2>&1
schtasks /delete /tn "MovoPc" /f >nul 2>&1

echo   Autostart removed.
echo   Stopping the running server ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5888" ^| findstr "LISTENING"') do taskkill /pid %%p /f >nul 2>&1

echo   Done.
ping -n 4 127.0.0.1 >nul
exit /b 0
