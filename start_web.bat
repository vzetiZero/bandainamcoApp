@echo off
chcp 65001 >nul
title NAMCO Account Manager - Web UI
cd /d "%~dp0web"

if not exist node_modules (
    echo [INFO] Cai dat thu vien web ^(lan dau, can Node.js^)...
    call npm.cmd install --no-fund --no-audit
    if errorlevel 1 (
        echo [LOI] npm install that bai. Kiem tra Node.js da cai chua.
        pause
        exit /b 1
    )
)

echo.
echo Giao dien: http://localhost:3000
echo Nho chay start_api.bat truoc (API cong 8787).
echo.
call npm.cmd run dev
pause
