@echo off
setlocal
cd /d "%~dp0"

REM Deliberately ASCII-only. cmd.exe reads .bat files using the OEM codepage
REM (CP950 on zh-TW Windows), so UTF-8 Chinese in a batch file renders as
REM garbage. Keeping this file plain English sidesteps the problem entirely.

echo ===== Voice Input - environment setup =====
echo.

REM --- Python 3.12 check ------------------------------------------------
REM The version must be 3.12: some dependencies do not publish wheels for
REM every Python version, and a 3.13 venv builds fine and then fails during
REM pip install with an error that gives no hint about the real cause. So
REM this checks first and stops, instead of falling back to whatever
REM "python" happens to resolve to.
REM
REM Two ways to find it. The py launcher is preferred because it can pick
REM 3.12 even when several versions are installed -- but it is not always
REM present (Microsoft Store installs and some others skip it), so fall
REM back to plain "python" and verify that it really is 3.12.
set "PY_CMD="

py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3.12"
    goto :have_python
)

python --version 2>nul | findstr /r /c:"^Python 3\.12\." >nul
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :have_python
)

echo [ERROR] Python 3.12 was not found.
echo.
echo This project requires Python 3.12 specifically.
echo Download a 3.12.x installer from https://www.python.org/downloads/
echo During installation, tick "Add python.exe to PATH".
echo Then run this script again.
echo.
if not defined CI pause
exit /b 1

:have_python
echo Using: %PY_CMD%
echo Creating virtual environment ^(.venv^) ...
%PY_CMD% -m venv .venv || goto :venv_failed

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo.
echo Installing pinned dependencies from requirements.lock.txt ...
pip install -r requirements.lock.txt || goto :pip_failed

echo.
echo ===== Setup complete =====
echo.
echo Next: double-click the .vbs launcher in this folder to start the app.
echo A first-run wizard will check your hardware and download the model.
echo.
echo Optional: the Breeze-ASR-25 engine is deprecated and needs ~1GB more.
echo Install it only if you want it:
echo     .venv\Scripts\pip install -r requirements-breeze.txt
echo.
if not defined CI pause
exit /b 0

:venv_failed
echo.
echo [ERROR] Could not create the virtual environment in .venv
echo If an old .venv folder exists and is broken, delete it and retry.
if not defined CI pause
exit /b 1

:pip_failed
echo.
echo [ERROR] Dependency installation failed - see the messages above.
echo A network problem is the most common cause; check your connection
echo and run this script again.
if not defined CI pause
exit /b 1
