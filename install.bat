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

echo.
echo ==========================================
echo    [OK] CAI DAT HOAN TAT!
echo ==========================================
echo.
echo Ban co the chay ung dung bang file start.bat
echo.
pause

