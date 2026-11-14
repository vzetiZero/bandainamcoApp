@echo off
chcp 65001 >nul
title NAMCO Account Manager - Cai dat
cd /d "%~dp0"

echo ==========================================
echo    NAMCO Account Manager - Cai dat
echo ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chua cai Python. Tai tai https://www.python.org/downloads/
    echo       Nho tick "Add Python to PATH".
    pause
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chua cai Node.js. Tai tai https://nodejs.org/ ^(ban LTS^)
    pause
    exit /b 1
)

echo [INFO] Cap nhat pip...
python -m pip install --upgrade pip

echo [INFO] Cai Python packages (requirements.txt)...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [LOI] pip install that bai.
    pause
    exit /b 1
)

:: Chrome that tren may duoc dung (channel="chrome") - khong can tai Chromium rieng.
echo [INFO] Cai chrome-devtools-mcp (dung de soi trang)...
call npm.cmd i -g chrome-devtools-mcp

echo [INFO] Cai thu vien UI (web/)...
pushd "%~dp0web"
call npm.cmd install --no-fund --no-audit
popd

echo [INFO] Cai Electron (desktop/)...
pushd "%~dp0desktop"
call npm.cmd install --no-fund --no-audit
if not exist "node_modules\electron\dist\electron.exe" (
    echo [INFO] Tai binary Electron (npm co the chan postinstall)...
    node node_modules\electron\install.js
)
popd

echo [INFO] Build giao dien tinh (web/out)...
pushd "%~dp0web"
call npm.cmd run build
popd

echo.
echo ==========================================
echo    [OK] CAI DAT HOAN TAT - chay start.bat
echo ==========================================
pause
