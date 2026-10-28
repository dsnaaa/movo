@echo off
chcp 65001 >nul
title Movo auto logon (disable)

rem  Undoes enable-autologon.bat: restores the normal login screen.

net session >nul 2>&1
if errorlevel 1 goto noadmin

reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultDomainName /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /f >nul 2>&1

echo   OK - auto logon disabled. The login screen is back.
ping -n 4 127.0.0.1 >nul
exit /b 0

:noadmin
echo   Administrator rights required.
echo   Right-click this file and choose "Run as administrator".
pause
exit /b 1
