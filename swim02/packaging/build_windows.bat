@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
REM ============================================================
REM  SWIM-AI - build the Windows distribution
REM   1) uses the project .venv (run.bat creates it if needed)
REM   2) installs PyInstaller
REM   3) builds dist\SWIM-AI\SWIM-AI.exe   (portable folder)
REM   4) if Inno Setup is installed, also builds
REM      dist\SWIM-AI-Setup.exe  (single installer)
REM ============================================================
title SWIM-AI Build
cd /d "%~dp0\.."      REM project root

set "VPY=%CD%\.venv\Scripts\python.exe"
if not exist "%VPY%" (
    echo [ERROR] .venv not found. Double-click run.bat first, then run this again.
    pause
    exit /b 1
)

echo ============================================================
echo   Building SWIM-AI
echo ============================================================
echo.

echo [1/4] Installing the build tool (PyInstaller) ...
"%VPY%" -m pip install --upgrade -q pyinstaller
if errorlevel 1 goto failed

echo [2/4] Checking dependencies ...
"%VPY%" -c "import numpy, cv2, mediapipe, PySide6, pyqtgraph" >nul 2>nul
if errorlevel 1 (
    echo       installing requirements first ...
    "%VPY%" -m pip install -r requirements.txt -c constraints.txt
    REM  headless cv2 on top of mediapipe opencv-contrib: never uninstall
    REM  opencv-contrib - it deletes the shared cv2 files
    "%VPY%" -m pip install --force-reinstall --no-deps -q opencv-python-headless
)

echo [3/4] Building the application folder (this takes a few minutes) ...
"%VPY%" -m PyInstaller --noconfirm --clean packaging\swim_ai.spec
if errorlevel 1 goto failed

if not exist "dist\SWIM-AI\SWIM-AI.exe" goto failed
echo.
echo       Built: dist\SWIM-AI\SWIM-AI.exe

echo [4/4] Looking for Inno Setup ...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
where iscc >nul 2>nul && if not defined ISCC set "ISCC=iscc"

if defined ISCC (
    echo       found, building the installer ...
    "%ISCC%" packaging\installer.iss
    if errorlevel 1 goto installer_failed
    echo       Built: dist\SWIM-AI-Setup.exe
) else (
    echo       Inno Setup not installed - skipping the single-file installer.
    echo       Download it from https://jrsoftware.org/isdl.php
    echo       then run this file again. The portable folder is ready to use.
)

echo.
echo ============================================================
echo   Done. Sizes:
"%VPY%" -c "import os;r='dist/SWIM-AI';t=sum(os.path.getsize(os.path.join(d,f)) for d,_,fs in os.walk(r) for f in fs);p='dist/SWIM-AI-Setup.exe';print('    dist/SWIM-AI          :', round(t/1048576), 'MB');print('    dist/SWIM-AI-Setup.exe:', round(os.path.getsize(p)/1048576), 'MB') if os.path.exists(p) else print('    installer             : not built')"
echo ============================================================
pause
exit /b 0

:installer_failed
echo.
echo [ERROR] Inno Setup failed. The portable folder in dist\SWIM-AI is fine.
pause
exit /b 1

:failed
echo.
echo [ERROR] Build failed. See the messages above.
pause
exit /b 1
