@echo off
title ICT screener
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m ict.live.screener
echo.
echo The screener has stopped.
pause
