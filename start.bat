@echo off
chcp 65001 >nul
title NAMCO Account Manager
cd /d "%~dp0"

echo ==========================================
echo    NAMCO Account Manager - khoi dong
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
    echo [LOI] Chua cai Node.js. Tai tai https://nodejs.org/ ^(LTS^)
    pause
    exit /b 1
)

:: Mot lenh duy nhat: cai thieu, build UI neu can, giai phong cong, mo API + Electron
python start.py %*

echo.
echo [INFO] Ung dung da dong.
pause
