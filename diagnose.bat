@echo off
REM ============================================================
REM  Setargan-Darya diagnostics (engine test, no window)
REM  Forwards to swim02\diagnose.bat. You may drop a video file
REM  onto this file to test that exact video.
REM ============================================================
call "%~dp0swim02\diagnose.bat" %*
exit /b %errorlevel%
