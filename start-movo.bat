@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Movo 5888

set "PORT=5888"
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 goto already

echo Starting Movo on https://127.0.0.1:%PORT%/ ...
echo Keep this window open. Close it to stop the server.
echo.
".venv\Scripts\python.exe" server.py
echo.
echo Server stopped. Press any key to close.
pause >nul
exit /b 0

:already
echo.
echo   Movo is already running on port %PORT%.
echo   Phone: https://192.168.31.12:%PORT%/
echo.
echo   Use restart-movo.bat if you want to restart it.
ping -n 6 127.0.0.1 >nul
exit /b 0
