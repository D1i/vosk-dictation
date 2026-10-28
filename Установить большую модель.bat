@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set LOG=build\install_model.log
set ZIP=%USERPROFILE%\Downloads\vosk-model-ru-0.42.zip
echo === установка большой модели %date% %time% === > "%LOG%"
if not exist "%ZIP%" ( echo НЕ НАЙДЕН архив: %ZIP% & echo нет архива >> "%LOG%" & pause & exit /b 1 )

echo [1/3] Распаковываю модель локально (быстро)...
echo tar -xf >> "%LOG%"
tar -xf "%ZIP%" -C models >> "%LOG%" 2>&1
if not exist "models\vosk-model-ru-0.42\am\final.mdl" (
  echo    tar не сработал, пробую PowerShell...
  echo Expand-Archive >> "%LOG%"
  powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath 'models' -Force" >> "%LOG%" 2>&1
)
if not exist "models\vosk-model-ru-0.42\am\final.mdl" (
  echo ОШИБКА: распаковка не удалась. Смотри build\install_model.log
  echo РАСПАКОВКА НЕ УДАЛАСЬ >> "%LOG%"
  type "%LOG%" & pause & exit /b 1
)
echo    Распаковано успешно.

echo [2/3] Прописываю большую модель в настройки...
".venv\Scripts\python.exe" -c "import json; p='config.json'; d=json.load(open(p,encoding='utf-8')); d['model_path']='models/vosk-model-ru-0.42'; json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=1); print('model_path =',d['model_path'])" >> "%LOG%" 2>&1

echo [3/3] Перезапускаю приложение с новой моделью...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_discord.ps1" >> "%LOG%" 2>&1
echo === готово %date% %time% === >> "%LOG%"

echo.
echo ==================== ГОТОВО ====================
echo Большая модель установлена, приложение перезапущено.
echo Первая загрузка тяжёлой модели занимает 10-30 секунд.
echo Можно закрывать окно.
timeout /t 25
