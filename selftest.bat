@echo off
REM ============================================================
REM  Setargan-Darya UI self test
REM  Forwards to swim02\selftest.bat. Run it if the app opens
REM  and closes, or shows a wrong layout.
REM ============================================================
call "%~dp0swim02\selftest.bat" %*
exit /b %errorlevel%
