@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
REM ============================================================
REM  Setargan-Darya Windows launcher
REM  - Doble-click this file. It does everything by itself.
REM  - Uses the project's .venv if it already exists (even when the
REM    system Python is 3.15 or newer), otherwise builds it with
REM    Python 3.10 - 3.14 and installs the dependencies.
REM  - Pass --safe to force software rendering (no OpenGL)
REM
REM  NOTE: the Python one-liners below must not contain cmd
REM  metacharacters such as carets or parentheses; keep them simple.
REM ============================================================
title Setargan-Darya Launcher
cd /d "%~dp0"

set "SAFE_MODE=0"
if /I "%~1"=="--safe" set "SAFE_MODE=1"
if /I "%~1"=="--no-gl" set "SAFE_MODE=1"

echo ============================================================
echo   Setargan-Darya - Swimming Biomechanics Analyzer
if "%SAFE_MODE%"=="1" echo   [SAFE MODE] Software rendering, no OpenGL
echo ============================================================
echo.

set "VPY=%CD%\.venv\Scripts\python.exe"
set "VCHECK=import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,10),(3,11),(3,12),(3,13),(3,14)) else 1)"
set "VENV_OK=0"
set "PYCMD="

REM --- 1. Is there already a working virtual environment? ------------
if exist "%VPY%" (
    "%VPY%" -c "%VCHECK%" >nul 2>nul
    if not errorlevel 1 set "VENV_OK=1"
)

if "%VENV_OK%"=="1" goto venv_ready

REM --- 2. No usable .venv: locate a supported Python ------------------
echo [1/4] Looking for Python 3.10 - 3.14 ...
echo.

REM (a) the official py launcher - 3.12 first, it has the best wheel support
where py >nul 2>nul
if not errorlevel 1 (
    for %%V in (3.12 3.13 3.11 3.10 3.14) do (
        if not defined PYCMD (
            py -%%V -c "%VCHECK%" >nul 2>nul
            if not errorlevel 1 set "PYCMD=py -%%V"
        )
    )
)

REM (b) plain "python" on PATH
if not defined PYCMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "%VCHECK%" >nul 2>nul
        if not errorlevel 1 set "PYCMD=python"
    )
)

REM (c) default per-user / per-machine install folders
if not defined PYCMD (
    for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" "%ProgramFiles%\Python312\python.exe" "C:\Python312\python.exe") do (
        if not defined PYCMD (
            if exist "%%~P" (
                "%%~P" -c "%VCHECK%" >nul 2>nul
                if not errorlevel 1 set PYCMD="%%~P"
            )
        )
    )
)

if not defined PYCMD goto no_python

echo [OK] Found: %PYCMD%
%PYCMD% --version
echo.

REM A leftover .venv built by an unsupported Python must be removed first
if exist "%VPY%" (
    echo [WARN] Removing the old .venv, it was built with an unsupported Python.
    rmdir /s /q ".venv"
)

echo [2/4] Creating virtual environment .venv ...
%PYCMD% -m venv .venv
if errorlevel 1 goto venv_failed
if not exist "%VPY%" goto venv_failed

:venv_ready
REM --- 3. Dependencies -------------------------------------------------
"%VPY%" -c "import cv2, numpy, mediapipe, PySide6, pyqtgraph" >nul 2>nul
if not errorlevel 1 goto cv_check

echo [3/4] Installing dependencies. This can take a few minutes ...
echo       Please keep this window open.
echo.
"%VPY%" -m pip install --upgrade pip -q
"%VPY%" -m pip install -r requirements.txt -c constraints.txt
if errorlevel 1 goto deps_failed

"%VPY%" -c "import cv2, numpy, mediapipe, PySide6, pyqtgraph" >nul 2>nul
if errorlevel 1 goto deps_failed

:cv_check
REM  OpenCV 5 + MediaPipe = a silent crash while the pose model is built.
REM  This repairs an already-broken .venv before the app starts, so the
REM  user never has to delete the folder by hand.
set "CV_CHECK=import sys, cv2; raise SystemExit(0 if int(cv2.__version__.split('.')[0]) < 5 else 1)"
"%VPY%" -c "%CV_CHECK%" >nul 2>nul
if not errorlevel 1 goto run_app

echo [3/4] Fixing the OpenCV version in .venv. This takes about a minute ...
"%VPY%" -m pip install -q -c constraints.txt --force-reinstall --no-deps "opencv-python-headless>=4.8,<5"
"%VPY%" -c "%CV_CHECK%" >nul 2>nul
if errorlevel 1 goto cv_failed

:run_app
REM --- 4. Start the app -------------------------------------------------
echo [4/4] Starting Setargan-Darya ...
echo.
set "SETARGAN_NO_PAUSE=1"
set "SAFE_ARGS="
if "%SAFE_MODE%"=="1" (
    set "SETARGAN_NO_GL=1"
    set "SAFE_ARGS=--no-gl"
    echo   Software rendering mode is ON
)
"%VPY%" run.py %SAFE_ARGS%
set "RC=%errorlevel%"

echo.
echo ============================================================
if not "%RC%"=="0" (
    echo  Setargan-Darya stopped with an error. Error code: %RC%
    echo.
    echo  جزئیات کامل:
    echo     %~dp0crash_log.txt
    echo.
    echo  کارهایی که می‌توانید امتحان کنید:
    echo     ۱- دابل‌کلیک روی selftest.bat   می‌گوید کدام بخش مشکل دارد
    echo     ۲- دابل‌کلیک روی run_debug.bat   حالت امن، بدون OpenGL
    echo     ۳- اجرای  doctor.py  برای بررسی محیط
    echo     ۴- اگر پنجره اصلا باز نشد، فایل crash_log.txt را بفرستید
) else (
    echo  Setargan-Darya closed.
)
echo ============================================================
pause
exit /b %RC%

REM ====================================================================
REM  Error handlers
REM ====================================================================
:no_python
echo [ERROR] No supported Python found - need Python 3.10 to 3.14.
echo.
echo Versions visible on this machine:
python --version 2>nul
py -0p 2>nul
echo.
echo راهنمای فارسی:
echo   ۱- اگر پایتون شما 3.15 یا جدیدتر است، هنوز پشتیبانی نمی‌شود.
echo      فقط Python 3.12 را نصب کنید، در همین پنجره این خط را بزنید:
echo.
echo         winget install -e --id Python.Python.3.12
echo.
echo      یا از این آدرس دانلود کنید:
echo         https://www.python.org/downloads/
echo      هنگام نصب تیک Add python.exe to PATH را بزنید.
echo   ۲- بعد از نصب یک بار این پنجره را ببندید و دوباره run.bat را
echo      دابل‌کلیک کنید. نیازی به تایپ هیچ دستور دیگری نیست.
echo.
pause
exit /b 1

:venv_failed
echo [ERROR] Could not create .venv with %PYCMD%
echo        Try installing Python 3.12 from python.org, then run run.bat again.
pause
exit /b 1

:deps_failed
echo.
echo [ERROR] Installing the libraries failed.
echo         Check the internet connection and try again.
echo         Manual command inside this folder:
echo             .venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
pause
exit /b 1

:cv_failed
echo.
echo [ERROR] OpenCV could not be repaired. An internet connection is needed.
echo         Manual command inside this folder:
echo             .venv\Scripts\python.exe -m pip install -c constraints.txt --force-reinstall --no-deps opencv-python-headless
pause
exit /b 1
