@echo off
chcp 65001 >nul
title NAMCO Account Manager - API backend
cd /d "%~dp0"

python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Cai dat FastAPI/uvicorn...
    python -m pip install fastapi "uvicorn[standard]"
)

echo.
echo API: http://127.0.0.1:8787   (tai lieu: http://127.0.0.1:8787/docs)
echo Giao dien web: mo cua so khac va chay start_web.bat
echo.
python server.py --no-browser
pause
