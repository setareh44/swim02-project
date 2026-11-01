@echo off
REM ============================================================
REM  SWIM-AI safe-mode launcher
REM  Same as run.bat but the moving background uses software
REM  rendering (no OpenGL). Use this if the window opens and
REM  closes immediately or looks black.
REM ============================================================
call "%~dp0run.bat" --safe
