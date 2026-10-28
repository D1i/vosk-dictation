@echo off
rem Create "Vosk Dictation" shortcuts on the Desktop and in the Start menu.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -ShortcutsOnly
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" pause
exit /b %CODE%
