@echo off
chcp 65001 >nul
title Movo auto logon (enable)

rem ------------------------------------------------------------
rem  Makes Windows log in automatically at boot, so the Movo
rem  autostart (Startup folder) runs right after power-on.
rem
rem  WHY: mouse/keyboard injection needs an interactive desktop
rem  session, so the service can only be useful after logon.
rem
rem  WARNING: anyone who powers on this PC gets into the desktop
rem  without a password. Use only on a trusted machine.
rem  If you sign in with a PIN, enter the ACCOUNT PASSWORD here.
rem  Requires: Run as administrator.
rem ------------------------------------------------------------

net session >nul 2>&1
if errorlevel 1 goto noadmin

echo This makes Windows skip the login screen at boot.
echo.
echo   WARNING: anyone who turns on this PC will get into your
echo   desktop without a password. Only do this on a trusted PC.
echo.
set "AU_USER="
set /p AU_USER=Windows user name (press Enter for %USERNAME%): 
if "%AU_USER%"=="" set "AU_USER=%USERNAME%"
set "AU_PASS="
set /p AU_PASS=Password (visible while typing, Enter for empty): 

reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d 1 /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /t REG_SZ /d "%AU_USER%" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultDomainName /t REG_SZ /d "%COMPUTERNAME%" /f >nul
if not "%AU_PASS%"=="" reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /t REG_SZ /d "%AU_PASS%" /f >nul

echo.
echo   OK - auto logon enabled for "%AU_USER%".
echo   Reboot to test. To undo, run disable-autologon.bat.
ping -n 6 127.0.0.1 >nul
exit /b 0

:noadmin
echo   Administrator rights required.
echo   Right-click this file and choose "Run as administrator".
pause
exit /b 1
