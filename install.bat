@echo off
title NAMCO Account Manager - Cai dat
color 0A

echo ==========================================
echo    NAMCO Account Manager - Cai dat
echo ==========================================
echo.

:: Kiem tra Python da cai dat chua
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chua cai dat Python!
    echo Vui long cai dat Python tu https://www.python.org/downloads/
    echo Nho tick vao "Add Python to PATH" khi cai dat.
    pause
    exit /b 1
)

echo [OK] Da tim thay Python:
python --version
echo.

:: Nang cap pip
echo [INFO] Dang cap nhat pip...
python -m pip install --upgrade pip
echo.

:: Cai dat thu vien
echo [INFO] Dang cai dat cac thu vien...
echo.

python -m pip install requests
if errorlevel 1 (
    echo [LOI] Khong the cai dat requests!
    pause
    exit /b 1
)

python -m pip install PySide6
if errorlevel 1 (
    echo [LOI] Khong the cai dat PySide6!
    pause
    exit /b 1
)

:: Playwright chi can cho phan chay chien dich bang trinh duyet.
:: Chrome that tren may duoc dung (channel="chrome"), KHONG can tai Chromium rieng.
echo [INFO] Dang cai dat Playwright (tuy chon, cho phan chay bang Chrome)...
python -m pip install playwright
if errorlevel 1 (
    echo [CANH BAO] Khong cai duoc Playwright - phan chay bang Chrome se khong dung duoc.
)

:: chrome-devtools-mcp: dung de soi trang/ snapshot. Thieu no thi app van chay.
echo [INFO] Dang cai chrome-devtools-mcp (can Node.js)...
where node >nul 2>&1
if errorlevel 1 (
    echo [CANH BAO] Chua co Node.js - bo qua chrome-devtools-mcp.
) else (
    call npm.cmd i -g chrome-devtools-mcp
)

:: Web UI (Next.js) + API FastAPI
echo [INFO] Dang cai FastAPI/uvicorn cho API...
python -m pip install fastapi "uvicorn[standard]"

echo [INFO] Dang cai thu vien cho giao dien web (web/)...
where node >nul 2>&1
if errorlevel 1 (
    echo [CANH BAO] Chua co Node.js - khong cai duoc giao dien web.
) else (
    pushd "%~dp0web"
    call npm.cmd install --no-fund --no-audit
    popd
)


echo.
echo ==========================================
echo    [OK] CAI DAT HOAN TAT!
echo ==========================================
echo.
echo Ban co the chay ung dung bang file start.bat
echo.
pause

