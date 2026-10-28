@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set LOG=build\hf_download.log
echo === Hugging Face download %date% %time% === > "%LOG%"
echo [1/2] Устанавливаю huggingface_hub (нужно один раз)...
".venv\Scripts\python.exe" -m pip install -q -U huggingface_hub >> "%LOG%" 2>&1
echo [2/2] Качаю модель alphacep/vosk-model-ru с Hugging Face...
echo    (файл ~2 ГБ, быстрый CDN — обычно несколько минут; прогресс идёт в окне)
".venv\Scripts\python.exe" -c "from huggingface_hub import snapshot_download; p=snapshot_download('alphacep/vosk-model-ru', local_dir=r'models/vosk-model-ru-big'); print('DONE', p)" 2>>"%LOG%" 1>>"%LOG%"
echo === finished %date% %time% === >> "%LOG%"
echo.
echo =================== РЕЗУЛЬТАТ ===================
findstr /C:"DONE" "%LOG%" >nul && (echo УСПЕХ: модель скачана.) || (echo ОШИБКА — последние строки лога:)
powershell -NoProfile -Command "Get-Content -Tail 15 -Encoding utf8 '%LOG%'"
echo.
echo Можно закрывать окно. Я (ассистент) уже вижу результат.
timeout /t 40
