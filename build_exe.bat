@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  Movo single-file EXE builder
echo ========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found in PATH.
    pause
    exit /b 1
)

echo [1/3] Installing build dependencies...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [ERROR] failed to install dependencies.
    pause
    exit /b 1
)

echo [2/3] Generating Windows icon...
python -c "from PIL import Image; im=Image.open(r'static/app-icon.png').convert('RGBA'); sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]; im.save(r'build/app-icon.ico', format='ICO', sizes=sizes); print('wrote build/app-icon.ico')"
if errorlevel 1 (
    echo [ERROR] failed to generate icon.
    pause
    exit /b 1
)

echo [3/3] Packaging with PyInstaller (MovoServer.spec)...
if not exist "build" mkdir build
python -m PyInstaller --noconfirm --clean MovoServer.spec
if errorlevel 1 (
    echo.
    echo [ERROR] packaging failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build finished.
echo  Output: %cd%\dist\MovoServer.exe
echo ========================================
echo.
explorer /select,"%cd%\dist\MovoServer.exe"
pause
