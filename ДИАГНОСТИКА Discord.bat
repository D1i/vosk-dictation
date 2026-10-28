@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
".venv\Scripts\python.exe" "tools\discord_probe.py"
echo.
timeout /t 20
