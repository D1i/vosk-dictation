"""Значок в трее (pystray, свой поток) и автозапуск через реестр."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

import config

log = logging.getLogger("tray")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "VoskDictation"


# ---------------------------------------------------------------- autostart
def autostart_command() -> str:
    return f'"{pythonw_path()}" "{os.path.join(config.APP_DIR, "main.pyw")}"'


def autostart_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_VALUE)
            return True
    except OSError:
        return False


def set_autostart(on: bool) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if on:
            winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_VALUE)
            except FileNotFoundError:
                pass


def open_in_notepad(path: str) -> None:
    subprocess.Popen(["notepad.exe", path], close_fds=True)


# ------------------------------------------------------------------ shortcut
_SHORTCUT_PS1 = """param([string]$Lnk, [string]$Exe, [string]$Main, [string]$Dir, [string]$Icon)
$ErrorActionPreference = 'Stop'
$ws = New-Object -ComObject WScript.Shell
$l = $ws.CreateShortcut($Lnk)
$l.TargetPath = $Exe
$l.Arguments = '"' + $Main + '"'
$l.WorkingDirectory = $Dir
$l.IconLocation = $Icon + ',0'
$l.Description = 'Голосовой ввод (Ctrl+Space)'
$l.Save()
"""


def pythonw_path() -> str:
    exe = sys.executable
    folder, name = os.path.split(exe)
    if name.lower() == "python.exe" and os.path.exists(os.path.join(folder, "pythonw.exe")):
        exe = os.path.join(folder, "pythonw.exe")
    return exe


def create_desktop_shortcut() -> str:
    """Ярлык «Vosk Dictation» на рабочем столе. Возвращает путь к ярлыку."""
    import ctypes
    import tempfile

    buf = ctypes.create_unicode_buffer(260)
    # CSIDL_DESKTOPDIRECTORY = 0x10 (учитывает перенос рабочего стола в OneDrive)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) != 0:
        raise OSError("не найдена папка рабочего стола")
    lnk = os.path.join(buf.value, f"{config.APP_NAME}.lnk")
    fd, script = tempfile.mkstemp(suffix=".ps1", prefix="vosk-shortcut-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
            f.write(_SHORTCUT_PS1)
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", script, "-Lnk", lnk, "-Exe", pythonw_path(),
             "-Main", os.path.join(config.APP_DIR, "main.pyw"), "-Dir", config.ROOT_DIR,
             "-Icon", os.path.join(config.APP_DIR, "assets", "icon.ico")],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0 or not os.path.exists(lnk):
            raise OSError((r.stderr or r.stdout or "powershell error").strip()[:300])
    finally:
        try:
            os.remove(script)
        except OSError:
            pass
    log.info("desktop shortcut created: %s", lnk)
    return lnk


_DISCORD_SETUP = 'Как подписывать реплики никами из Discord\n==========================================\n\nЧтобы в логах разговора вместо «Собеседник» стояли настоящие ники, программа\nспрашивает у запущенного Discord, кто сейчас говорит. Для этого нужно один раз\nсоздать своё бесплатное приложение Discord и вписать два значения в настройки.\nДанные остаются на вашем компьютере, ничего никуда не отправляется, кроме самого\nDiscord. Доступ только на чтение (кто в канале и кто говорит) — писать сообщения\nили менять аккаунт программа не может.\n\nШаги\n----\n1. Откройте https://discord.com/developers/applications и войдите под своим\n   аккаунтом Discord.\n2. Нажмите «New Application», придумайте имя (например, «Мои логи») → Create.\n3. Слева откройте вкладку «OAuth2».\n   * В разделе «Redirects» нажмите «Add Redirect» и впишите ровно:\n        http://localhost\n     Нажмите «Save Changes» внизу.\n4. На вкладке «OAuth2» (или «General Information») скопируйте:\n   * CLIENT ID  — длинное число;\n   * CLIENT SECRET — нажмите «Reset Secret» / «Copy» и скопируйте строку\n     (её видно один раз — если потеряете, сбросьте заново).\n5. В открывшемся рядом файле config.json впишите их в кавычки:\n        "discord_client_id": "СЮДА_CLIENT_ID",\n        "discord_client_secret": "СЮДА_CLIENT_SECRET",\n   Сохраните файл (Файл → Сохранить).\n6. В меню значка в трее выберите «Применить настройки».\n7. Убедитесь, что Discord запущен. При первом подключении Discord покажет окно\n   «… запрашивает доступ» — нажмите «Авторизовать». Это нужно один раз.\n\nГотово. Зайдите в голосовой канал — запись начнётся сама (если включён пункт\n«Начинать при входе в голосовой канал»), и реплики будут подписаны никами.\n\nЕсли ников нет, а стоит «Собеседник»\n------------------------------------\n* Discord должен быть запущен и вы должны быть в голосовом канале.\n* Проверьте, что client_id и client_secret вписаны без пробелов и в кавычках.\n* Redirect в приложении Discord — ровно http://localhost\n* Подробности — в logs\\app.log.\n\nВажно\n-----\nЗаписывать разговоры можно не везде и не всегда законно. Предупреждайте\nсобеседников о записи и соблюдайте правила сервера и законы вашей страны.\n'


def write_discord_setup() -> str:
    """Кладёт рядом с программой инструкцию по подключению Discord. Возвращает путь."""
    path = os.path.join(config.ROOT_DIR, "Discord \u2014 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430.txt")
    try:
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(_DISCORD_SETUP)
    except OSError:
        log.exception("cannot write discord setup")
    return path


# --------------------------------------------------------------------- tray
class Tray:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self._imgs = {}

    def _image(self, state: str):
        img = self._imgs.get(state)
        if img is None:
            from painter import Painter
            img = Painter().app_icon(state, 64)
            self._imgs[state] = img
        return img

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True, name="tray")
        self.thread.start()

    def _title(self, listening: bool) -> str:
        hk = self.app.hotkey_label()
        base = f"{config.APP_NAME} — {'слушаю' if listening else 'готов'} ({hk})"
        if getattr(self.app, "recording", False):
            base += " · запись разговора"
        return base

    def _run(self) -> None:
        try:
            import pystray
            from pystray import Menu, MenuItem as Item

            app = self.app

            def toggle_autostart(icon, item):
                try:
                    set_autostart(not autostart_enabled())
                except OSError:
                    log.exception("autostart toggle failed")
                icon.update_menu()

            def make_shortcut(icon, item):
                def work():
                    try:
                        create_desktop_shortcut()
                        self.notify("Ярлык «Vosk Dictation» создан на рабочем столе")
                    except Exception as e:  # noqa: BLE001
                        log.exception("shortcut failed")
                        self.notify(f"Не удалось создать ярлык: {e}")
                threading.Thread(target=work, daemon=True, name="shortcut").start()

            def open_logs(icon, item):
                path = os.path.join(config.LOG_DIR, "app.log")
                if os.path.exists(path):
                    open_in_notepad(path)

            def open_talks(icon, item):
                from recorder import talks_dir
                try:
                    os.startfile(talks_dir())
                except OSError:
                    log.exception("open talks failed")

            def setup_discord(icon, item):
                write_discord_setup()
                try:  # дописать в config.json новые поля discord_*, если их ещё нет
                    config.update({})
                except OSError:
                    log.exception("config migrate failed")
                open_in_notepad(os.path.join(config.ROOT_DIR, "Discord — настройка.txt"))
                open_in_notepad(config.CONFIG_PATH)

            def talk_toggle(icon, item):
                app.post_talk_toggle()

            def toggle_talk_autostart(icon, item):
                new = not app.cfg.get("talk_autostart_on_channel", True)
                app.cfg["talk_autostart_on_channel"] = new
                try:
                    config.update({"talk_autostart_on_channel": new})
                except OSError:
                    log.exception("save setting failed")
                icon.update_menu()

            talk_menu = Menu(
                Item(lambda item: ("Остановить запись" if app.recording
                                   else "Начать запись") +
                     (f" ({app.talk_hotkey_label()})" if app.talk_hotkey_label() else ""),
                     talk_toggle),
                Item("Начинать при входе в голосовой канал", toggle_talk_autostart,
                     checked=lambda item: bool(app.cfg.get("talk_autostart_on_channel", True))),
                Menu.SEPARATOR,
                Item("Открыть папку с логами разговоров", open_talks),
                Item("Настроить Discord (ники)…", setup_discord),
            )

            def make_model_item(mname):
                def label(item):
                    low = mname.lower()
                    tag = "  (маленькая, быстрая)" if "small" in low else "  (большая, точнее)"
                    return mname + tag
                return Item(label,
                            (lambda n: (lambda icon, item: app.post_set_model(n)))(mname),
                            checked=(lambda n: (lambda item: app.current_model_name() == n))(mname),
                            radio=True)
            _model_names = app.available_models()
            if _model_names:
                model_menu = Menu(*[make_model_item(m) for m in _model_names])
            else:
                model_menu = Menu(Item("(в папке models нет моделей)", None, enabled=False))

            menu = Menu(
                Item(lambda item: f"Включить / выключить микрофон ({app.hotkey_label()})",
                     lambda icon, item: app.post_toggle(), default=True),
                Menu.SEPARATOR,
                Item("Настройки (config.json)", lambda icon, item: open_in_notepad(config.CONFIG_PATH)),
                Item("Применить настройки", lambda icon, item: app.post_reload()),
                Item("Модель распознавания", model_menu),
                Menu.SEPARATOR,
                Item(lambda item: "● Запись разговора" if app.recording else "Запись разговора",
                     talk_menu),
                Menu.SEPARATOR,
                Item("Запускать при входе в Windows", toggle_autostart,
                     checked=lambda item: autostart_enabled()),
                Item("Ярлык на рабочем столе", make_shortcut),
                Item("Открыть журнал", open_logs),
                Item("Открыть папку приложения", lambda icon, item: os.startfile(config.ROOT_DIR)),
                Menu.SEPARATOR,
                Item("Выход", lambda icon, item: app.post_quit()),
            )
            self.icon = pystray.Icon("VoskDictation", self._image("loading"),
                                     self._title(False), menu)
            self.icon.run()
        except Exception:  # noqa: BLE001
            log.exception("tray failed")

    def set_listening(self, on: bool) -> None:
        icon = self.icon
        if icon is None:
            return
        try:
            icon.icon = self._image("icon" if on else "loading")
            icon.title = self._title(on)
        except Exception:  # noqa: BLE001
            log.exception("tray update failed")

    def refresh(self) -> None:
        icon = self.icon
        if icon is None:
            return
        try:
            listening = self.app.session is not None
            icon.icon = self._image("icon" if (listening or self.app.recording) else "loading")
            icon.title = self._title(listening)
            icon.update_menu()
        except Exception:  # noqa: BLE001
            log.exception("tray refresh failed")

    def notify(self, text: str) -> None:
        try:
            if self.icon is not None:
                self.icon.notify(text, config.APP_NAME)
        except Exception:  # noqa: BLE001
            log.exception("notify failed")

    def stop(self) -> None:
        try:
            if self.icon is not None:
                self.icon.stop()
            # дождаться, пока значок уберётся из трея (иначе останется «призрак»)
            if getattr(self, "thread", None) is not None:
                self.thread.join(timeout=2.0)
        except Exception:  # noqa: BLE001
            log.exception("tray stop failed")
