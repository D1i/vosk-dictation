@echo off
rem Typing methods test: after start you have 4 seconds to click into the target window.
setlocal
cd /d "%~dp0.."
start "" "%CD%\.venv\Scripts\pythonw.exe" "%CD%\tests\typing_test.py" %*
