@echo off
setlocal EnableDelayedExpansion

REM ====================================================
REM Hat Yai Flood Intelligence - Auto Setup & Run Script
REM ====================================================

cd /d "%~dp0"

REM 1. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python from https://www.python.org/
    pause
    exit /b
)

REM 2. Check/Create Virtual Environment
if not exist ".venv" (
    echo [INFO] Virtual environment not found. Creating one...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b
    )
    echo [SUCCESS] Virtual environment created.
)

REM 3. Activate Virtual Environment
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

REM 4. Install/Update Dependencies
if exist ".venv\installed.flag" (
    echo [INFO] Dependencies already installed. Skipping check.
    goto :run_app
)

echo [INFO] Installing dependencies (First time only)...
python -m pip install --upgrade pip
pip install -r requirement.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b
)
REM Create a flag file to indicate successful installation
type nul > ".venv\installed.flag"

:run_app
REM 5. Run the Application
echo.
echo [INFO] Starting Hat Yai Flood Intelligence Dashboard...
echo [INFO] Press Ctrl+C to stop the server.
echo.
streamlit run app.py

pause
