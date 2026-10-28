@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Movo setup (new PC)

rem ------------------------------------------------------------
rem  One-time setup for a new computer.
rem  Usage:  setup-new-pc.bat              (install directly)
rem          setup-new-pc.bat 1.2.3.4:7890 (install via http proxy)
rem ------------------------------------------------------------

if exist ".venv\Scripts\python.exe" goto venvok

echo Creating virtual environment .venv ...
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)

if not exist ".venv\Scripts\python.exe" goto nopython

:venvok
if "%~1"=="" goto noproxy

echo.
echo Installing dependencies via proxy %~1 ...
".venv\Scripts\python.exe" -m pip install --proxy "http://%~1" -r requirements.txt
goto done

:noproxy
echo.
echo Installing dependencies (no proxy) ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
goto done

:done
echo.
echo ============================================
echo   Setup finished.
echo   Next: run start-movo.bat
echo ============================================
pause
exit /b 0

:nopython
echo.
echo   [x] Python not found.
echo   Install Python 3.10+ from python.org first
echo   (check "Add python.exe to PATH" during install),
echo   then run this script again.
pause
exit /b 1
