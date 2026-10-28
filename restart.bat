@echo off
rem Restart Vosk Dictation in normal mode (after the demo or a crash).
setlocal
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0app\main.pyw" --quit >nul 2>&1
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app\main.pyw"
