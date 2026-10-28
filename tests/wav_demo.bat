@echo off
rem Demo without a microphone: restarts Vosk Dictation so that it "hears"
rem tests\test_ru.wav instead of the microphone. Click into any text field
rem (for example Notepad) and press Ctrl+Space - the phrase from the recording
rem will be typed. To return to normal mode run restart.bat in the project folder.
setlocal
cd /d "%~dp0.."
set "PYW=%CD%\.venv\Scripts\pythonw.exe"
set "PY=%CD%\.venv\Scripts\python.exe"
"%PY%" "%CD%\app\main.pyw" --quit >nul 2>&1
start "" "%PYW%" "%CD%\app\main.pyw" --wav "%CD%\tests\test_ru.wav" --log-text
