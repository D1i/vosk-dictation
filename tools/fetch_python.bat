@echo off
rem Downloads the embeddable Python from python.org into build\ (needed by tools\build_dist.py).
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fetch_python.ps1" %*
echo.
timeout /t 15
