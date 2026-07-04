@echo off
setlocal
cd /d "%~dp0"

set "VENV=collector-venv"
set "PY=%VENV%\Scripts\python.exe"

REM ── Pick a base Python interpreter (py launcher, else python) ────────────────
set "BASEPY="
where py >nul 2>&1 && set "BASEPY=py"
if not defined BASEPY (
    where python >nul 2>&1 && set "BASEPY=python"
)
if not defined BASEPY (
    echo [ERROR] Python was not found on this computer.
    echo Install Python 3.12+ from https://www.python.org/downloads/ and re-run.
    pause
    exit /b 1
)

REM ── Create the virtual environment on first run (venvs are NOT portable, so
REM    we always build a fresh, machine-local one) ──────────────────────────────
if not exist "%PY%" (
    echo Creating virtual environment in "%VENV%" ...
    %BASEPY% -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
    set "FRESH=1"
)

REM ── Install dependencies only when the venv was just created ────────────────
REM If "collector-venv" already exists, skip installation entirely.
if defined FRESH (
    echo Installing dependencies ...
    "%PY%" -m pip install --upgrade pip >nul 2>&1
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. Check your internet connection.
        pause
        exit /b 1
    )
) else (
    echo Existing "%VENV%" found - skipping dependency installation.
)

REM ── Apply database migrations (seeds countries / zones) ─────────────────────
echo Applying database migrations ...
"%PY%" "ui\manage.py" migrate --noinput
if errorlevel 1 (
    echo [ERROR] Database migration failed.
    pause
    exit /b 1
)

REM ── Start the server and open the browser ───────────────────────────────────
echo Starting server...
start "Data Collector" "%PY%" "ui\manage.py" runserver 0.0.0.0:8000

:wait
timeout /t 1 /nobreak >nul
curl -s http://localhost:8000 >nul 2>&1
if errorlevel 1 goto wait

echo Server ready. Opening browser...
start "" http://localhost:8000

endlocal
