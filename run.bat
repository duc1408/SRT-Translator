@echo off
title SRT Subtitle Translator

:: ── Detect Python ─────────────────────────────────────────────
set "PYTHON_EXE="

:: 1. Check Python 3.10 local install
set "LOCAL_PY=%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe"
if exist "%LOCAL_PY%" (
    set "PYTHON_EXE=%LOCAL_PY%"
    goto :found
)

:: 2. Check Python 3.11
set "LOCAL_PY=%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
if exist "%LOCAL_PY%" (
    set "PYTHON_EXE=%LOCAL_PY%"
    goto :found
)

:: 3. Check Python 3.12
set "LOCAL_PY=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
if exist "%LOCAL_PY%" (
    set "PYTHON_EXE=%LOCAL_PY%"
    goto :found
)

:: 4. Fallback to PATH
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto :found
)

echo.
echo [!] ERROR: Python not found!
echo     Please install Python 3.10+ from https://python.org
echo.
pause
exit /b 1

:found
echo [*] Python: %PYTHON_EXE%

:: ── Check Python version ───────────────────────────────────────
"%PYTHON_EXE%" -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [!] Python 3.8+ required. Please upgrade.
    pause
    exit /b 1
)

:: ── Launch app ─────────────────────────────────────────────────
cd /d "%~dp0"
echo [*] Starting SRT Subtitle Translator...
echo.
"%PYTHON_EXE%" app.py

echo.
echo [x] App closed.
pause
