@echo off
rem Run with a console log (for troubleshooting). Close this window or press Ctrl+C to exit.
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" "%~dp0app\main.pyw" --quit >nul 2>&1
"%~dp0.venv\Scripts\python.exe" "%~dp0app\main.pyw" --console %*
pause
