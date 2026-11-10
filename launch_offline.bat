@echo off
setlocal enabledelayedexpansion
title WinFix AI - Offline Web Host

echo ========================================================
echo   WinFix AI - Local Offline Web Server
echo ========================================================
echo.

cd /d "%~dp0"

:: 1. Detect Python executable in .venv or system PATH
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

:: 2. Verify Python availability
"%PY_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python environment not found.
    echo Please make sure .venv exists or Python is installed.
    echo.
    pause
    exit /b 1
)

echo [OK] Python detected: %PY_EXE%
echo [OK] Offline Mode Enforced
echo.
echo ========================================================
echo   Starting web server on local URL:
echo     Local URL:   http://localhost:8501
echo     Loopback:    http://127.0.0.1:8501
echo ========================================================
echo.

"%PY_EXE%" "%~dp0winfix_launcher.py" --host 127.0.0.1 --port 8501

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application terminated with exit code: %errorlevel%
    pause
)
