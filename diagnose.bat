@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
REM ============================================================
REM  SWIM-AI - عیب‌یابی بسته‌شدن ناگهانی برنامه
REM  همین فایل را دابل‌کلیک کنید. موتور تحلیل را بدون پنجره
REM  اجرا می‌کند تا معلوم شود مشکل از MediaPipe/OpenCV است یا
REM  از رابط کاربری (OpenGL).
REM  اگر ویدیوی خاصی مشکل دارد، آن را روی همین فایل بکشید و رها کنید.
REM ============================================================
title SWIM-AI Diagnostics
cd /d "%~dp0"

set "VPY=%CD%\.venv\Scripts\python.exe"
if not exist "%VPY%" goto no_venv

echo ============================================================
echo   SWIM-AI - آزمون موتور تحلیل (بدون پنجره)
echo ============================================================
echo.

if "%~1"=="" (
    "%VPY%" tools\diagnose_engine.py
) else (
    "%VPY%" tools\diagnose_engine.py "%~1"
)

echo.
echo ============================================================
echo   فایل‌های گزارش:
echo     %CD%\fatal.log
echo     %CD%\console.log
echo     %CD%\system_info.txt
echo.
echo   اگر برنامه در حین «تحلیل» بسته می‌شود، همین فایل‌ها را
echo   برای پشتیبانی بفرستید.
echo ============================================================
pause
exit /b 0

:no_venv
echo [ERROR] پوشه .venv پیدا نشد.
echo         اول یک بار run.bat را دابل‌کلیک کنید، بعد این فایل را.
echo.
pause
exit /b 1
