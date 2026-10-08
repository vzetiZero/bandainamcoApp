@echo off
title NAMCO Account Manager - Start
color 0A

echo ==========================================
echo    NAMCO Account Manager - Khoi dong
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

:: Kiem tra va cai dat thu vien neu can
echo [INFO] Kiem tra thu vien can thiet...
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Dang cai dat requests...
    pip install requests
)

python -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Dang cai dat PySide6...
    pip install PySide6
)

echo [OK] Tat ca thu vien da san sang!
echo.

:: Chay ung dung
echo [INFO] Dang khoi dong ung dung...
echo.
python account_manager.py

if errorlevel 1 (
    echo.
    echo [LOI] Ung dung da gap loi!
    pause
)

