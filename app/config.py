"""Настройки приложения: config.json в корне проекта."""
from __future__ import annotations

import copy
import json
import logging
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(APP_DIR)
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")
LOG_DIR = os.path.join(ROOT_DIR, "logs")

APP_NAME = "Vosk Dictation"

HELP = {
    "hotkey": "Горячая клавиша: ctrl+space, ctrl+alt+d, win+shift+s, f9 ...",
    "model_path": "Папка модели Vosk (относительно папки приложения или абсолютный путь)",
    "input_device": "Микрофон: null = системный по умолчанию, число = индекс, строка = часть названия",
    "auto_stop_silence_sec": "Выключать микрофон после стольких секунд без речи (0 = никогда)",
    "typing_method": "clipboard = вставка через буфер обмена (по умолчанию; буфер потом восстанавливается), unicode = посимвольный ввод",
    "paste_keys": "Чем вставлять: ctrl+v (по умолчанию) или shift+insert",
    "per_app_typing": "Способ ввода для отдельных программ, например {\"mintty.exe\": \"unicode\"}",
    "newline_key": "Только для unicode: чем печатать «новая строка» — shift+enter или enter",
    "voice_punctuation": "Голосовые знаки: «точка», «запятая», «вопросительный знак», «новая строка»...",
    "capitalize": "Заглавная буква в начале диктовки и после . ! ?",
    "space_after_dictation": "Пробел после текста, когда микрофон выключается (чтобы следующая диктовка не слиплась)",
    "sounds": "Короткий звук при включении/выключении микрофона",
    "show_partial_text": "Показывать распознаваемый текст в плашке",
    "replacements": "Свои замены: что говорите -> что печатать",
    "log_text": "Писать распознанный текст в logs/app.log (для отладки)",
    "_запись_разговора": "Ниже — запись разговора в текст (например, из Discord)",
    "talk_autostart_on_channel": "Автоматически начинать запись при входе в голосовой канал Discord",
    "talk_record_mic": "Записывать и свой микрофон (ваши реплики)",
    "talk_output_device": "Динамики для записи собеседников: null = системные, или часть названия",
    "talk_input_device": "Микрофон для записи: null = системный, или часть названия",
    "talk_merge_gap_sec": "Склеивать подряд реплики одного человека, если пауза меньше стольких секунд",
    "talk_hotkey": "Горячая клавиша «начать/остановить запись разговора» (пусто = только меню)",
    "discord_client_id": "ID вашего приложения Discord (discord.com/developers) — чтобы подписывать реплики никами",
    "discord_client_secret": "Client Secret того же приложения Discord",
}

DEFAULTS: dict = {
    "hotkey": "ctrl+space",
    "model_path": "models/vosk-model-small-ru-0.22",
    "input_device": None,
    "auto_stop_silence_sec": 30,
    "typing_method": "clipboard",
    "paste_keys": "ctrl+v",
    "per_app_typing": {},
    "newline_key": "shift+enter",
    "voice_punctuation": True,
    "capitalize": True,
    "space_after_dictation": True,
    "sounds": True,
    "show_partial_text": True,
    "replacements": {"гитхаб": "GitHub"},
    "log_text": False,
    "talk_autostart_on_channel": True,
    "talk_record_mic": True,
    "talk_output_device": None,
    "talk_input_device": None,
    "talk_merge_gap_sec": 6,
    "talk_hotkey": "",
    "discord_client_id": "",
    "discord_client_secret": "",
}

log = logging.getLogger("config")


def _write_default() -> None:
    data = {"_справка": HELP}
    data.update(copy.deepcopy(DEFAULTS))
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load() -> tuple[dict, str | None]:
    """Возвращает (настройки, текст ошибки или None)."""
    cfg = copy.deepcopy(DEFAULTS)
    if not os.path.exists(CONFIG_PATH):
        try:
            _write_default()
        except OSError as e:
            log.warning("cannot write default config: %s", e)
        return cfg, None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            user = json.load(f)
        if not isinstance(user, dict):
            raise ValueError("ожидался JSON-объект")
    except Exception as e:  # noqa: BLE001
        log.error("config.json error: %s", e)
        return cfg, f"Ошибка в config.json: {e}"
    for k, v in user.items():
        if not k.startswith("_"):
            cfg[k] = v
    return cfg, None


def update(changes: dict) -> None:
    """Меняет отдельные значения в config.json, сохраняя остальное и справку."""
    data = {"_справка": HELP}
    data.update(copy.deepcopy(DEFAULTS))
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                cur = json.load(f)
            if isinstance(cur, dict):
                data.update(cur)
        except (OSError, ValueError):
            pass
    data["_справка"] = HELP
    data.update(changes)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def mtime() -> float:
    try:
        return os.path.getmtime(CONFIG_PATH)
    except OSError:
        return 0.0


def model_dir(cfg: dict) -> str:
    p = os.path.expandvars(os.path.expanduser(str(cfg.get("model_path") or "")))
    if not os.path.isabs(p):
        p = os.path.join(ROOT_DIR, p)
    return os.path.normpath(p)
