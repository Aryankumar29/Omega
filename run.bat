@echo off
title Omega Outreach Engine
echo ==========================================
echo    Omega Outreach Engine
echo ==========================================
echo.

cd /d "%~dp0"

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    echo Installing dependencies...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo Starting Omega on http://localhost:5000
echo Press Ctrl+C to stop
echo.
python app.py
pause
