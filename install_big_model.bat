@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist build mkdir build
echo START %date% %time% > build\extract.log
echo(
echo ============================================
echo   Extracting vosk-model-ru-0.42 (~3.7 GB)
echo   This can take 1-3 minutes. Please wait...
echo ============================================
echo(
tar -xf "%USERPROFILE%\Downloads\vosk-model-ru-0.42.zip" -C models >> build\extract.log 2>&1
if exist "models\vosk-model-ru-0.42\graph\HCLG.fst" goto ok
echo tar failed or incomplete, trying PowerShell Expand-Archive... >> build\extract.log
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath ('{0}\Downloads\vosk-model-ru-0.42.zip' -f $env:USERPROFILE) -DestinationPath 'models' -Force" >> build\extract.log 2>&1
if exist "models\vosk-model-ru-0.42\graph\HCLG.fst" goto okps
echo RESULT=FAILED >> build\extract.log
echo(
echo Extraction FAILED. See build\extract.log
goto end
:ok
echo RESULT=DONE-TAR %date% %time% >> build\extract.log
echo(
echo Extraction complete (tar).
goto end
:okps
echo RESULT=DONE-PS %date% %time% >> build\extract.log
echo(
echo Extraction complete (PowerShell).
:end
echo Log: build\extract.log
timeout /t 12 >nul
