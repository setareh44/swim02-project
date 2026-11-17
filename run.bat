@echo off
REM ============================================================
REM  Setargan-Darya root launcher
REM  The real project lives in the swim02\ folder (it has app\,
REM  tools\, models\). This file only forwards there, so you can
REM  double-click run.bat from EITHER folder - same result.
REM ============================================================
call "%~dp0swim02\run.bat" %*
exit /b %errorlevel%
