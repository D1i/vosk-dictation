@echo off
rem Build dist\ (installer + portable zip) on Windows. Needs NSIS 3 (makensis) and
rem build\python-3.12.10-embed-amd64.zip (tools\fetch_python.bat).
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1
"%~dp0..\.venv\Scripts\python.exe" "%~dp0build_dist.py" %*
echo.
pause
