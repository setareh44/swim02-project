@echo off
chcp 65001 >nul
setlocal
REM ============================================================
REM  SWIM-AI - UI self test
REM  Checks that the window, its pages, the background animation
REM  and the About dialog can actually be built on THIS machine.
REM  Run it if the app opens and closes, or shows a wrong layout.
REM  Nothing is changed; a report is written to ui_selftest.log
REM ============================================================
cd /d "%~dp0"
set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
"%VPY%" -c "import PySide6" >nul 2>nul
if errorlevel 1 goto no_qt
"%VPY%" "%~dp0tools\selftest_ui.py" --no-pause
goto done

:no_qt
echo ============================================================
echo  PySide6 is not installed in .venv yet.
echo  Please run run.bat first - it installs everything, then
echo  run this self test again.
echo ============================================================

:done
echo.
pause
