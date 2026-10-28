@echo off
rem Diagnostics: Python, packages, audio devices, microphone test, model test.
rem The report is saved to logs\diagnose.txt and opened in Notepad.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
set "OUT=%~dp0logs\diagnose.txt"
set "PY=%~dp0.venv\Scripts\python.exe"
echo Vosk Dictation diagnostics > "%OUT%"
echo %DATE% %TIME% >> "%OUT%"
ver >> "%OUT%"
if not exist "%PY%" (
  echo .venv not found - run install.bat first >> "%OUT%"
  goto done
)
echo. >> "%OUT%"
echo ===== python ===== >> "%OUT%"
"%PY%" -c "import sys, vosk, sounddevice, pystray, PIL; print(sys.version); print('sounddevice', sounddevice.__version__, '| PortAudio', sounddevice.get_portaudio_version()[1]); print('Pillow', PIL.__version__)" >> "%OUT%" 2>&1
echo. >> "%OUT%"
echo ===== devices ===== >> "%OUT%"
"%PY%" "%~dp0app\main.pyw" --list-devices >> "%OUT%" 2>&1
echo. >> "%OUT%"
echo ===== microphone ===== >> "%OUT%"
"%PY%" "%~dp0app\main.pyw" --mic-test >> "%OUT%" 2>&1
echo. >> "%OUT%"
echo ===== recognition ===== >> "%OUT%"
"%PY%" "%~dp0app\main.pyw" --selftest "%~dp0tests\test_ru.wav" >> "%OUT%" 2>&1
echo. >> "%OUT%"
echo ===== conversation recording ===== >> "%OUT%"
"%PY%" -c "import soundcard, numpy; print('soundcard', soundcard.__version__ if hasattr(soundcard,'__version__') else 'ok', '| numpy', numpy.__version__)" >> "%OUT%" 2>&1
"%PY%" "%~dp0app\main.pyw" --loop-test >> "%OUT%" 2>&1
:done
echo. >> "%OUT%"
echo ===== end ===== >> "%OUT%"
if /i not "%~1"=="--no-open" start "" notepad.exe "%OUT%"
