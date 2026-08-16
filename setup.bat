@echo off
setlocal
cd /d "%~dp0"

REM Deliberately ASCII-only. cmd.exe reads .bat files using the OEM codepage
REM (CP950 on zh-TW Windows), so UTF-8 Chinese in a batch file renders as
REM garbage. Keeping this file plain English sidesteps the problem entirely.

echo ===== Voice Input - environment setup =====
echo.

REM --- Python 3.12 check ------------------------------------------------
REM No silent fallback to whatever "python" resolves to. Some dependencies
REM do not publish wheels for every Python version, so a 3.13 venv gets
REM built successfully and then fails during pip install with an error
REM that gives no hint about the real cause.
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.12 was not found.
    echo.
    echo This project requires Python 3.12 specifically.
    echo Download a 3.12.x installer from https://www.python.org/downloads/
    echo During installation, tick "Add python.exe to PATH".
    echo Then run this script again.
    echo.
    pause
    exit /b 1
)

echo Creating virtual environment ^(.venv^) with Python 3.12 ...
py -3.12 -m venv .venv || goto :venv_failed

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
pause
exit /b 0

:venv_failed
echo.
echo [ERROR] Could not create the virtual environment in .venv
echo If an old .venv folder exists and is broken, delete it and retry.
pause
exit /b 1

:pip_failed
echo.
echo [ERROR] Dependency installation failed - see the messages above.
echo A network problem is the most common cause; check your connection
echo and run this script again.
pause
exit /b 1
