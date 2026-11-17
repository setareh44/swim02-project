@echo off
REM ============================================================
REM  Setargan-Darya safe-mode launcher (no OpenGL)
REM  Forwards to swim02\run.bat --safe - use this if the window
REM  opens and closes immediately or looks black.
REM ============================================================
call "%~dp0swim02\run.bat" --safe
exit /b %errorlevel%
