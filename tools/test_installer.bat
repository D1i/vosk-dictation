@echo off
rem Test dist\VoskDictation-*-setup.exe: silent install into build\test-install, checks, uninstall.
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_installer.ps1"
echo.
timeout /t 20
