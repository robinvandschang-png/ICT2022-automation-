@echo off
title ICT screener - Telegram test
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m ict.live.notify
echo.
pause
