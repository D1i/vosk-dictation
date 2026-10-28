# Vosk Dictation — заметки для Claude

Локальный голосовой ввод для Windows на Python 3.12 и Vosk. Устройство приложения — в [ARCHITECTURE.md](ARCHITECTURE.md), пользовательская документация — в [README.md](README.md); здесь они не дублируются.

## Стек и окружение
- Python 3.12, окружение `.venv`, зависимости в `requirements.txt` (vosk, sounddevice, pystray, Pillow, soundcard, numpy).
- Только Windows: ctypes-обёртки Win32, SendInput, буфер обмена, именованный канал Discord.
- Не JS-проект: Jest, Vite, Playwright, Cypress, Rust/WASM здесь не используются.
- `.venv/`, `models/`, `logs/`, `build/`, `dist/` не в git. После клона запустить `install.bat`: он создаёт `.venv`, ставит зависимости и скачивает `vosk-model-small-ru-0.22`.

## Команды
Пути относительно корня проекта.

| Задача | Команда |
|---|---|
| Запуск | `.venv\Scripts\pythonw.exe app\main.pyw` |
| Запуск с логом в консоли | `.venv\Scripts\python.exe app\main.pyw --console` |
| Проверка модели на файле | `.venv\Scripts\python.exe app\main.pyw --selftest tests\test_ru.wav` |
| Диагностика звука | `app\main.pyw` с `--list-devices`, `--mic-test`, `--loop-test`, `--talk-test СЕК` |
| Вкл/выкл и закрытие запущенной копии | `.venv\Scripts\pythonw.exe app\main.pyw --toggle` / `--quit` |
| Перезапуск | `restart.bat` |
| Сборка установщика и portable zip | `tools\build_dist.bat`: нужны NSIS 3 и `build\python-3.12.10-embed-amd64.zip` (`tools\fetch_python.bat`); перезаписывает `dist\` |
| Проверка установщика | `tools\test_installer.bat` |
| Линтер | не настроен |

## Тесты
Фреймворка нет: три самостоятельных скрипта, запуск из корня проекта.

```
.venv\Scripts\python.exe -u -X utf8 tests\test_textproc.py
.venv\Scripts\python.exe -u -X utf8 tests\test_recorder.py
.venv\Scripts\python.exe -u -X utf8 tests\test_app_flow.py
```

- `-u` обязателен при перенаправлении вывода: `test_recorder.py` и `test_app_flow.py` завершаются через `os._exit(0)`, буфер stdout теряется.
- `test_textproc.py` — форматирование текста (чистая логика). `test_recorder.py` — диаризация, лог и обмен RPC с фальшивым Discord в памяти. `test_app_flow.py` — логика `App` с заглушками winapi, overlay, hotkey, tray, typer и vosk.
- `tests\typing_test.py` (`typing_test.bat`) и `tests\wav_demo.bat` — ручные, печатают в активное окно. Автоматически не запускать.
- Разделения Jest / Playwright / Cypress, компонентных и e2e-тестов нет. Живое приложение проверяется вручную или через `--selftest`.
- Известный сбой (на 2026-10-28): `test_recorder.py` падает в `test_rpc_with_token` с `'FakeDiscord' object has no attribute 'wait_readable'`. В `PipeTransport` (`app/rpc.py`) метод есть, заглушка `FakeDiscord` в тесте его не получила. Прод-код не затронут, чинить надо заглушку.

## Соглашения
- Язык комментариев, докстрингов, текстов для пользователя и коммитов — русский.
- Окончания строк задаёт `.gitattributes`: `.bat`, `.ps1`, `.nsi`, `packaging/dist/*.txt` — CRLF; `.py`, `.pyw`, `.md`, `.json` — LF. UTF-8 BOM у `.ps1` и `.nsi` нужен для кириллицы (Windows PowerShell 5.1, NSIS), не удалять.
- Правила `.gitignore` для каталогов привязаны к корню (`/dist/`, `/build/` и т. д.): `packaging/dist/` — исходники сборки, в игнор попадать не должен.
- Секреты не коммитить: `config.json` (Discord client id и secret), `discord_token.json` (OAuth-токены), любые `*.bak` (копии конфигов). Перед коммитом сверять `git ls-files`.
- Резервные копии `*.bak` рядом с исходниками не создавать: `tools/build_dist.py` их не пропускает и упакует `app/*.bak` в установщик.
- `config.json` приложение создаёт само из `DEFAULTS` в `app/config.py` при первом запуске, примера в репозитории нет.

## Git
- Ветка `main`, remote `origin` — `https://github.com/D1i/vosk-dictation.git`. Remote добавляет и пушит пользователь, Claude не пушит.
- Сообщения: Conventional Commits на русском (`feat(scope): описание`), как в соседнем проекте пользователя. Тело подробное, по пунктам, без `Co-Authored-By`. Хуков и commitlint в проекте нет.

## Журнал регресса
| Что | Дата | Результат |
|---|---|---|
| Полный регресс | не проводился | — |
| Прогон unit-скриптов | 2026-10-28 | `test_textproc` OK, `test_app_flow` OK, `test_recorder` красный (см. «Тесты») |
| Чистка мусора | 2026-10-28 | 8 файлов `*.bak` исключены из git, на диске не тронуты |
| Проверка кода | не проводилась | — |
