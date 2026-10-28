@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Movo restart

set "PORT=5888"
echo Stopping the instance on port %PORT% ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    taskkill /pid %%p /f >nul 2>&1
    echo   killed PID %%p
)
ping -n 2 127.0.0.1 >nul

echo Starting ...
echo.
".venv\Scripts\python.exe" server.py
echo.
echo Server stopped. Press any key to close.
pause >nul
exit /b 0
