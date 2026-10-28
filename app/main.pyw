"""Vosk Dictation — локальный голосовой ввод в любое поле по Ctrl+Space.

Запуск:  pythonw main.pyw                 — обычный режим (значок в трее)
         python  main.pyw --console       — с логом в консоли
         python  main.pyw --selftest X.wav — проверить модель на файле
         python  main.pyw --list-devices  — список микрофонов
         python  main.pyw --mic-test      — проверить, что микрофон отдаёт звук
         python  main.pyw --loop-test     — проверить запись звука из динамиков
         pythonw main.pyw --toggle        — включить/выключить в запущенной копии
         pythonw main.pyw --quit          — закрыть запущенную копию
         pythonw main.pyw --quit --only-from DIR — закрыть, только если она из папки DIR
         python  main.pyw --wav X.wav     — вместо микрофона «говорит» файл (для проверки)
"""
from __future__ import annotations

import argparse
import ctypes
import logging
import logging.handlers
import os
import sys
import threading
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import config  # noqa: E402

log = logging.getLogger("app")

WM_APP = 0x8000
WM_APP_TOGGLE = WM_APP + 1
WM_APP_AUTOSTOP = WM_APP + 2
WM_APP_MODEL = WM_APP + 3
WM_APP_RELOAD = WM_APP + 4
WM_APP_QUIT = WM_APP + 5
WM_APP_TALK_TOGGLE = WM_APP + 6
WM_APP_TALK_JOIN = WM_APP + 7
WM_APP_TALK_LEAVE = WM_APP + 8
WM_APP_TALK_STATE = WM_APP + 9
WM_APP_TALK_ERROR = WM_APP + 10
WM_APP_SET_MODEL = WM_APP + 11

MUTEX_NAME = "Local\\VoskDictation.SingleInstance"


def setup_logging(console: bool) -> None:
    if sys.stdout is None or sys.stderr is None:  # pythonw
        devnull = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull
    else:
        for s in (sys.stdout, sys.stderr):
            try:
                if s.isatty():
                    s.reconfigure(errors="replace")
                else:  # в файл/канал — всегда UTF-8 (встроенный Python не читает PYTHONUTF8)
                    s.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, OSError):
                pass
    os.makedirs(config.LOG_DIR, exist_ok=True)
    handlers: list[logging.Handler] = [logging.handlers.RotatingFileHandler(
        os.path.join(config.LOG_DIR, "app.log"), maxBytes=1_000_000, backupCount=2,
        encoding="utf-8")]
    if console:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")


def window_title() -> str:
    return f"{config.APP_NAME}|{config.ROOT_DIR}"


def same_dir(a: str, b: str) -> bool:
    def norm(p):
        return os.path.normcase(os.path.normpath(os.path.abspath(p.strip().strip('"'))))
    return bool(a.strip()) and bool(b.strip()) and norm(a) == norm(b)


def pretty_hotkey(spec: str) -> str:
    names = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift",
             "win": "Win", "space": "Space", "enter": "Enter", "esc": "Esc"}
    parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    return "+".join(names.get(p, p.upper() if len(p) <= 3 else p.capitalize()) for p in parts)


# ============================================================================ app
class App:
    def __init__(self, args):
        import winapi as wa
        from engine import ModelHolder
        from hotkey import GlobalHotkey
        from overlay import Overlay
        from tray import Tray
        from typer import ClipboardPaster, Typer

        self.wa = wa
        self.args = args
        self.cfg, cfg_err = config.load()
        self.cfg_mtime = config.mtime()
        self.session = None
        self.partial_text = ""
        self.session_text = ""
        self.flash_text = ""
        self.flash_hint = ""
        self.flash_until = 0.0
        # запись разговора
        self.recorder = None
        self.recording = False
        self.recording_auto = False
        self._talk_lock = threading.Lock()
        self._talk_state = ""
        self._talk_error = ""
        self.rpc = None
        self._rpc_stop = threading.Event()

        self.overlay = Overlay(self.on_message, self.view, window_title())
        self.hotkey = GlobalHotkey(self.overlay.hwnd)
        self.talk_hotkey = GlobalHotkey(self.overlay.hwnd, hotkey_id=0x5D1D)
        self.typer = Typer(lambda: self.cfg)
        self.typer.paster = ClipboardPaster(self.overlay.hwnd)
        self.typer.start()
        self.models = ModelHolder(config.model_dir(self.cfg))
        self.models.load_async(lambda: self.overlay.post(WM_APP_MODEL))
        self.tray = Tray(self)
        self.tray.start()

        err = self.hotkey.register(self.cfg.get("hotkey") or "ctrl+space")
        if cfg_err or err:
            self.flash(cfg_err or err, "Исправьте config.json и выберите «Применить настройки»", 8)
        self._register_talk_hotkey()
        self._init_recorder()
        self._start_rpc()
        log.info("started: hotkey=%s (%s), model=%s, wav=%s", self.hotkey.spec,
                 self.hotkey.mode, self.models.path, args.wav)

    # ---------------------------------------------------------------- helpers
    def hotkey_label(self) -> str:
        return pretty_hotkey(self.hotkey.spec or self.cfg.get("hotkey") or "ctrl+space")

    def post_toggle(self):
        self.overlay.post(WM_APP_TOGGLE)

    def post_talk_toggle(self):
        self.overlay.post(WM_APP_TALK_TOGGLE)

    def post_reload(self):
        self.overlay.post(WM_APP_RELOAD)

    def post_quit(self):
        self.overlay.post(WM_APP_QUIT)

    def post_set_model(self, name):
        self._pending_model = name
        self.overlay.post(WM_APP_SET_MODEL)

    def flash(self, text: str, hint: str = "", seconds: float = 4.0) -> None:
        log.warning("flash: %s | %s", text, hint)
        self.flash_text, self.flash_hint = text, hint
        self.flash_until = time.monotonic() + seconds
        if self.session is None:
            self.overlay.show()

    # ------------------------------------------------- выбор модели
    def available_models(self) -> list:
        mdir = os.path.join(config.ROOT_DIR, "models")
        res = []
        try:
            for n in sorted(os.listdir(mdir)):
                p = os.path.join(mdir, n)
                if os.path.isdir(p) and os.path.isdir(os.path.join(p, "am")):
                    res.append(n)
        except OSError:
            pass
        return res

    def current_model_name(self) -> str:
        p = (self.cfg.get("model_path") or "").replace("\\", "/").rstrip("/")
        return os.path.basename(p)

    def set_model(self, name: str) -> None:
        from engine import ModelHolder
        rel = "models/" + name
        self.cfg["model_path"] = rel
        try:
            config.update({"model_path": rel})
        except OSError:
            log.exception("save model_path failed")
        new_model = config.model_dir(self.cfg)
        if new_model != self.models.path:
            self.models = ModelHolder(new_model)
            if self.recorder is not None:
                try:
                    self.recorder.models = self.models
                except Exception:  # noqa: BLE001
                    pass
            self.models.load_async(lambda: self.overlay.post(WM_APP_MODEL))
            self.flash("Модель: " + name, "Загружаю… (большая модель — до минуты)", 8)
        self.tray.refresh()
        log.info("model switched -> %s", rel)

    # --------------------------------------------------- запись разговора
    def _init_recorder(self):
        from recorder import Recorder
        self.recorder = Recorder(self.models, self.cfg, on_state=self._on_talk_state)

    def _register_talk_hotkey(self):
        spec = (self.cfg.get("talk_hotkey") or "").strip()
        if not spec:
            self.talk_hotkey.unregister()
            return
        err = self.talk_hotkey.register(spec)
        if err:
            log.warning("talk hotkey: %s", err)

    def talk_hotkey_label(self) -> str:
        spec = (self.cfg.get("talk_hotkey") or "").strip()
        return pretty_hotkey(spec) if spec else ""

    # запуск/остановка (в UI-потоке, но тяжёлое — в отдельном потоке)
    def talk_toggle(self):
        if self.recording:
            self._talk_stop()
        else:
            self._talk_start(auto=False)

    def _talk_start(self, auto: bool):
        with self._talk_lock:
            if self.recording or self.recorder is None:
                return
            self.recording = True
            self.recording_auto = auto
        self.recorder.cfg = self.cfg
        name = self.recorder.channel_name

        def work():
            try:
                self.recorder.start(name)
                self.tray.refresh()
                self.flash("Запись разговора включена",
                           "Логи: logs\\talks · выключить — в меню значка", 3)
            except Exception as e:  # noqa: BLE001
                log.exception("talk start failed")
                with self._talk_lock:
                    self.recording = False
                self._talk_error = str(e)
                self.overlay.post(WM_APP_TALK_ERROR)
        threading.Thread(target=work, daemon=True, name="talk-start").start()

    def _talk_stop(self):
        with self._talk_lock:
            if not self.recording:
                return
            self.recording = False
            self.recording_auto = False

        def work():
            try:
                self.recorder.stop()
            except Exception as e:  # noqa: BLE001
                log.warning("talk stop: %s", e)
            self.tray.refresh()
            self.flash("Запись разговора выключена", "", 2)
        threading.Thread(target=work, daemon=True, name="talk-stop").start()

    def _on_talk_state(self, text: str):
        self._talk_state = text
        self.overlay.post(WM_APP_TALK_STATE)

    # колбэки Discord RPC (приходят из потоков RPC)
    def on_voice_channel(self, channel_id, names, merge=False, channel_name=None):
        if self.recorder is not None:
            self.recorder.on_voice_channel(channel_id, names, merge=merge,
                                           channel_name=channel_name)
        if not merge:
            self.overlay.post(WM_APP_TALK_JOIN if channel_id else WM_APP_TALK_LEAVE)

    def on_speaking(self, user_id, speaking, t):
        if self.recorder is not None:
            self.recorder.on_speaking(user_id, speaking, t)

    def on_self(self, user_id, nick):
        if self.recorder is not None:
            self.recorder.set_self(user_id, nick)

    def on_state(self, text):
        self._on_talk_state(text)

    # RPC живёт под присмотром: Discord может быть ещё не запущен — переподключаемся
    def _start_rpc(self):
        self._rpc_id = (self.cfg.get("discord_client_id") or "").strip()
        self._rpc_secret = (self.cfg.get("discord_client_secret") or "").strip()
        if not self._rpc_id:
            return
        self._rpc_stop.clear()
        threading.Thread(target=self._rpc_supervisor, daemon=True, name="rpc-sup").start()

    def _rpc_supervisor(self):
        import rpc as rpcmod
        store = rpcmod.TokenStore(os.path.join(config.ROOT_DIR, "discord_token.json"))
        while not self._rpc_stop.is_set():
            cid = (self.cfg.get("discord_client_id") or "").strip()
            secret = (self.cfg.get("discord_client_secret") or "").strip()
            if not cid:
                return
            client = rpcmod.RpcClient(cid, secret, store, self)
            self.rpc = client
            client.start()
            while client.is_alive() and not self._rpc_stop.is_set():
                client.join(timeout=0.5)
            if self._rpc_stop.is_set():
                client.stop()
                return
            # соединение оборвалось (Discord закрыт/перезапуск) — ждём и пробуем снова
            for _ in range(5):
                if self._rpc_stop.is_set():
                    return
                time.sleep(1.0)

    def _stop_rpc(self):
        self._rpc_stop.set()
        if self.rpc is not None:
            try:
                self.rpc.stop()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------- view
    def view(self):
        sess = self.session
        if sess is not None:
            hint = f"{self.hotkey_label()} — выключить"
            if not self.models.ready.is_set():
                return ("loading", "Загружаю модель…", False,
                        "Можно говорить — текст появится через пару секунд", 0.0)
            if sess.mic_silent:
                return ("error", "Микрофон не передаёт звук",
                        False, "Проверьте: Параметры → Конфиденциальность → Микрофон", 0.0)
            if self.cfg.get("show_partial_text", True):
                if self.partial_text:
                    return ("listening", (self.session_text + " " + self.partial_text).strip(),
                            False, hint, sess.level)
                if self.session_text:
                    return ("listening", self.session_text, True, hint, sess.level)
            return ("listening", "Говорите…", True, hint, sess.level)
        if self.flash_text and time.monotonic() < self.flash_until:
            return ("error", self.flash_text, False, self.flash_hint, 0.0)
        return None

    # --------------------------------------------- session callbacks (thread)
    def on_partial(self, sess, text):
        if sess is self.session:
            self.partial_text = text

    def on_final(self, sess, raw, typed):
        if sess is self.session:
            self.partial_text = ""
            self.session_text = (self.session_text + typed)[-400:]

    def on_auto_stop(self, sess):
        self.overlay.post(WM_APP_AUTOSTOP, sess.id)

    def on_ended(self, sess):
        log.info("session %s finished", sess.id)
        # если поток сессии завершился сам (ошибка) — выключаем и в интерфейсе
        self.overlay.post(WM_APP_AUTOSTOP, sess.id)

    # --------------------------------------------------------------- messages
    def on_message(self, msg, wp, lp):
        wa = self.wa
        if msg in (wa.WM_RENDERFORMAT, wa.WM_RENDERALLFORMATS, wa.WM_DESTROYCLIPBOARD):
            paster = self.typer.paster
            return paster.on_message(msg, wp, lp) if paster is not None else None
        if msg == wa.WM_HOTKEY:
            if wp == self.talk_hotkey.id:
                self.talk_toggle()
            else:
                self.toggle()
            return 0
        if msg == WM_APP_TOGGLE:
            self.toggle()
            return 0
        if msg == WM_APP_TALK_TOGGLE:
            self.talk_toggle()
            return 0
        if msg == WM_APP_TALK_JOIN:
            if self.cfg.get("talk_autostart_on_channel", True) and not self.recording:
                self._talk_start(auto=True)
            return 0
        if msg == WM_APP_TALK_LEAVE:
            if self.recording and self.recording_auto:
                self._talk_stop()
            return 0
        if msg == WM_APP_TALK_STATE:
            log.info("discord: %s", self._talk_state)
            self.tray.refresh()
            if "Разрешите доступ" in self._talk_state:
                self.flash(self._talk_state, "Нажмите «Авторизовать» в окне Discord", 12)
            return 0
        if msg == WM_APP_TALK_ERROR:
            self.tray.refresh()
            self.flash("Не удалось начать запись", self._talk_error, 8)
            return 0
        if msg == WM_APP_AUTOSTOP:
            if self.session is not None and self.session.id == wp:
                self.stop("silence")
            return 0
        if msg == WM_APP_MODEL:
            if self.models.error:
                self.stop("model error")
                self.flash("Модель Vosk не загрузилась",
                           "Запустите install.bat ещё раз · подробности в logs\\app.log", 10)
            return 0
        if msg == WM_APP_SET_MODEL:
            name = getattr(self, "_pending_model", None)
            if name:
                self.set_model(name)
            return 0
        if msg == WM_APP_RELOAD:
            self.reload(force=True)
            return 0
        if msg in (WM_APP_QUIT, wa.WM_CLOSE):
            self.quit()
            return 0
        if msg == wa.WM_DESTROY:
            wa.PostQuitMessage(0)
            return 0
        return None

    # ------------------------------------------------------------ dictation
    def toggle(self):
        if self.session is not None:
            self.stop("hotkey")
        else:
            self.start()

    def start(self):
        from engine import MicSource, Session, WavSource
        from textproc import Formatter
        import sounds

        if config.mtime() != self.cfg_mtime:
            self.reload()
        if self.models.ready.is_set() and self.models.model is None:
            self.flash("Модель Vosk не загрузилась",
                       "Запустите install.bat ещё раз · подробности в logs\\app.log", 6)
            return
        cfg = self.cfg
        fmt = Formatter(voice_punctuation=bool(cfg.get("voice_punctuation", True)),
                        capitalize=bool(cfg.get("capitalize", True)),
                        replacements=cfg.get("replacements") or {})
        sounds_on = bool(cfg.get("sounds", True))
        try:
            auto_stop = float(cfg.get("auto_stop_silence_sec", 30) or 0)
        except (TypeError, ValueError):
            auto_stop = 30.0
        sess = Session(self.models, fmt, self.typer, self,
                       auto_stop_sec=auto_stop,
                       skip_ms=250 if sounds_on else 0,
                       log_text=bool(cfg.get("log_text", False)) or self.args.log_text,
                       space_after=bool(cfg.get("space_after_dictation", True)))
        if self.args.wav:
            src = WavSource(self.args.wav, sess.feed)
        else:
            src = MicSource(cfg.get("input_device"), sess.feed)
        # сначала показываем плашку (первый кадр рисуется сразу), потом открываем микрофон
        self.session = sess
        self.partial_text = ""
        self.session_text = ""
        self.flash_text = ""
        self.overlay.show()
        try:
            sess.begin(src)
        except Exception:  # noqa: BLE001
            log.exception("cannot open audio source")
            self.session = None
            self.flash("Нет доступа к микрофону",
                       "Параметры Windows → Конфиденциальность → Микрофон", 6)
            return
        sounds.play("start", sounds_on)
        self.tray.set_listening(True)
        log.info("dictation on (session %s, source %s)", sess.id, src.name)

    def stop(self, reason: str):
        import sounds
        sess, self.session = self.session, None
        if sess is None:
            return
        sess.end()  # поток сессии допечатает хвост фразы сам
        sounds.play("stop", bool(self.cfg.get("sounds", True)))
        self.partial_text = ""
        self.overlay.hide()
        self.tray.set_listening(False)
        log.info("dictation off (session %s, %s)", sess.id, reason)

    # --------------------------------------------------------------- config
    def reload(self, force: bool = False):
        from engine import ModelHolder
        old_hotkey = self.hotkey.spec
        old_model = self.models.path
        cfg, err = config.load()
        self.cfg, self.cfg_mtime = cfg, config.mtime()
        new_hotkey = cfg.get("hotkey") or "ctrl+space"
        if force or new_hotkey != old_hotkey:
            herr = self.hotkey.register(new_hotkey)
            if herr:
                if old_hotkey and old_hotkey != new_hotkey:
                    self.hotkey.register(old_hotkey)
                err = err or herr
        new_model = config.model_dir(cfg)
        if new_model != old_model:
            self.models = ModelHolder(new_model)
            self.models.load_async(lambda: self.overlay.post(WM_APP_MODEL))
        self._register_talk_hotkey()
        if self.recorder is not None:
            self.recorder.cfg = cfg
        # если поменяли данные Discord — перезапускаем подключение
        old_id = (getattr(self, "_rpc_id", "") or "")
        old_secret = (getattr(self, "_rpc_secret", "") or "")
        new_id = (cfg.get("discord_client_id") or "").strip()
        new_secret = (cfg.get("discord_client_secret") or "").strip()
        if force or new_id != old_id or new_secret != old_secret:
            self._stop_rpc()
            self._start_rpc()
        self.tray.refresh()
        if err:
            self.flash(err, "Исправьте config.json и выберите «Применить настройки»", 8)
        log.info("config reloaded (hotkey=%s)", self.hotkey.spec)

    def quit(self):
        log.info("quit")
        # сторож: что бы ни зависло при закрытии — процесс гарантированно завершится
        threading.Timer(4.0, lambda: os._exit(0)).start()
        if self.session is not None:
            self.stop("quit")
        if self.recording:
            try:
                self.recorder.stop()
            except Exception:  # noqa: BLE001
                pass
            self.recording = False
        self._stop_rpc()
        self.hotkey.unregister()
        self.talk_hotkey.unregister()
        self.tray.stop()
        self.typer.stop()
        self.overlay.destroy()


# ======================================================================= modes
def selftest(wav_path: str) -> int:
    import json
    import wave
    from engine import ModelHolder
    from textproc import Formatter

    cfg, err = config.load()
    if err:
        print(err)
    mh = ModelHolder(config.model_dir(cfg))
    t0 = time.monotonic()
    mh.load()
    if mh.model is None:
        print(f"ОШИБКА: модель не загрузилась: {mh.error}")
        return 2
    print(f"Модель загружена за {time.monotonic() - t0:.1f} c: {mh.path}")
    from vosk import KaldiRecognizer
    with wave.open(wav_path, "rb") as wf:
        rec = KaldiRecognizer(mh.model, wf.getframerate())
        phrases = []
        t0 = time.monotonic()
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                t = json.loads(rec.Result()).get("text", "")
                if t:
                    phrases.append(t)
        t = json.loads(rec.FinalResult()).get("text", "")
        if t:
            phrases.append(t)
        dur = wf.getnframes() / wf.getframerate()
    fmt = Formatter(voice_punctuation=bool(cfg.get("voice_punctuation", True)),
                    capitalize=bool(cfg.get("capitalize", True)),
                    replacements=cfg.get("replacements") or {})
    typed = "".join(fmt.feed(p) for p in phrases)
    print(f"Аудио {dur:.1f} c распознано за {time.monotonic() - t0:.1f} c")
    for p in phrases:
        print(f"  фраза: {p}")
    print(f"Будет напечатано: {typed}")
    return 0 if typed else 1


def mic_test(seconds: float = 3.0) -> int:
    import array
    from engine import MicSource, level_of

    cfg, err = config.load()
    if err:
        print(err)
    chunks: list[bytes] = []
    src = MicSource(cfg.get("input_device"), chunks.append)
    try:
        src.open()
    except Exception as e:  # noqa: BLE001
        print(f"ОШИБКА: не удалось открыть микрофон: {e}")
        return 2
    print(f"Слушаю {seconds:.0f} c: {src.name} ({src.rate} Гц)…")
    time.sleep(seconds)
    src.close()
    data = b"".join(chunks)
    n = len(data) // 2
    print(f"Получено {n / src.rate:.1f} c звука")
    if not n:
        print("ОШИБКА: звук не поступает")
        return 3
    if data.count(0) == len(data):
        print("ОШИБКА: микрофон отдаёт тишину (одни нули). Проверьте: Параметры → "
              "Конфиденциальность и защита → Микрофон → доступ для классических приложений")
        return 4
    a = array.array("h")
    a.frombytes(data[: n * 2])
    peak = max(abs(x) for x in a) / 32768
    print(f"Пик: {peak:.3f}, громкость (0..1): {level_of(data):.2f}")
    print("OK: микрофон работает")
    return 0


def talk_test(seconds: float) -> int:
    """Полная проверка записи разговора без Discord: пишет N секунд и печатает лог."""
    import time as _t
    from engine import ModelHolder
    from recorder import Recorder
    cfg, err = config.load()
    if err:
        print(err)
    mh = ModelHolder(config.model_dir(cfg))
    print("Загружаю модель…")
    mh.load()
    if mh.model is None:
        print(f"ОШИБКА: модель не загрузилась: {mh.error}")
        return 2
    rec = Recorder(mh, cfg, on_state=lambda t: print("  ", t))
    try:
        rec.start("проверка")
    except Exception as e:  # noqa: BLE001
        print(f"ОШИБКА старта: {e}")
        return 3
    print(f"Пишу {seconds:.0f} c. Говорите в микрофон и/или включите русскую речь в динамиках…")
    _t.sleep(seconds)
    try:
        rec.stop()
    except Exception as e:  # noqa: BLE001
        print(f"Проблема дорожек: {e}")
    print(f"\nЛог: {rec.path}\n" + "-" * 40)
    try:
        print(open(rec.path, encoding="utf-8").read())
    except OSError as e:
        print("не удалось прочитать лог:", e)
    return 0


def loop_test(seconds: float = 6.0) -> int:
    """Записывает звук из динамиков (loopback) и распознаёт — проверка без Discord."""
    import json
    cfg, err = config.load()
    if err:
        print(err)
    try:
        from recorder import LoopbackSource, RATE
    except Exception as e:  # noqa: BLE001
        print(f"ОШИБКА: {e}")
        return 2
    src = LoopbackSource(cfg.get("talk_output_device"))
    try:
        src.open()
    except Exception as e:  # noqa: BLE001
        print(f"ОШИБКА: не удалось открыть звук динамиков: {e}")
        print("Нужны пакеты soundcard и numpy (ставит install.bat) и Windows 10/11.")
        return 3
    print(f"Пишу {seconds:.0f} c звука из «{src.name}». Включите звук/музыку/голос…")
    import time as _t
    chunks = []
    t0 = _t.monotonic()
    while _t.monotonic() - t0 < seconds:
        d = src.read()
        if d:
            chunks.append(d)
    src.close()
    raw = b"".join(chunks)
    if not raw or raw.count(0) == len(raw):
        print("Тишина: динамики ничего не воспроизводили (или не тот выход).")
        return 4
    mh = None
    try:
        from engine import ModelHolder
        mh = ModelHolder(config.model_dir(cfg))
        mh.load()
    except Exception:  # noqa: BLE001
        pass
    if mh and mh.model is not None:
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(mh.model, RATE)
        for i in range(0, len(raw), 8000):
            rec.AcceptWaveform(raw[i:i + 8000])
        text = json.loads(rec.FinalResult()).get("text", "")
        print(f"Распознано из динамиков: {text or '(речь не распознана — но звук идёт)'}")
    print("OK: запись звука из динамиков работает")
    return 0


def list_devices() -> int:
    import sounddevice as sd
    print(sd.query_devices())
    try:
        print("\nМикрофон по умолчанию:", sd.query_devices(None, "input")["name"])
    except Exception as e:  # noqa: BLE001
        print("\nМикрофон по умолчанию не найден:", e)
    return 0


def signal_running(msg: int, only_from: str | None = None) -> bool:
    import winapi as wa
    from overlay import CLASS_NAME
    hwnd = wa.FindWindowW(CLASS_NAME, None)
    if not hwnd:
        return False
    if only_from:
        title = wa.window_text(hwnd)
        running_root = title.split("|", 1)[1] if "|" in title else ""
        if not same_dir(running_root, only_from):
            log.info("running copy is from %r, not %r — left alone", running_root, only_from)
            return False
    wa.PostMessageW(hwnd, msg, 0, 0)
    if msg == WM_APP_QUIT:
        for _ in range(50):
            time.sleep(0.1)
            if not wa.FindWindowW(CLASS_NAME, None):
                break
    return True


def acquire_single_instance(wait_s: float = 6.0):
    """Мьютекс «одна копия». Если прежняя копия как раз закрывается
    (окна уже нет, а процесс ещё жив) — ждём её выхода."""
    import winapi as wa
    from overlay import CLASS_NAME
    deadline = time.monotonic() + wait_s
    while True:
        ctypes.set_last_error(0)
        h = wa.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.get_last_error() != wa.ERROR_ALREADY_EXISTS:
            return h
        wa.CloseHandle(h)
        if wa.FindWindowW(CLASS_NAME, None) or time.monotonic() > deadline:
            return None
        time.sleep(0.2)


def main() -> int:
    ap = argparse.ArgumentParser(description=config.APP_NAME)
    ap.add_argument("--console", action="store_true", help="лог в консоль")
    ap.add_argument("--selftest", metavar="WAV", help="распознать файл и выйти")
    ap.add_argument("--list-devices", action="store_true", help="список аудиоустройств")
    ap.add_argument("--mic-test", action="store_true", help="проверить микрофон (3 c)")
    ap.add_argument("--loop-test", action="store_true",
                    help="проверить запись звука из динамиков (loopback, 6 c)")
    ap.add_argument("--talk-test", type=float, metavar="СЕК", default=0,
                    help="проверка записи разговора: записать N секунд и показать лог")
    ap.add_argument("--log-text", action="store_true", help="писать распознанный текст в журнал")
    ap.add_argument("--wav", metavar="WAV", help="использовать файл вместо микрофона")
    ap.add_argument("--toggle", action="store_true", help="переключить диктовку в запущенной копии")
    ap.add_argument("--quit", action="store_true", help="закрыть запущенную копию")
    ap.add_argument("--only-from", metavar="DIR",
                    help="с --quit/--toggle: только если копия запущена из этой папки")
    args = ap.parse_args()

    setup_logging(args.console or bool(args.selftest) or args.list_devices or args.mic_test)
    if args.selftest:
        return selftest(args.selftest)
    if args.list_devices:
        return list_devices()
    if args.mic_test:
        return mic_test()
    if args.loop_test:
        return loop_test()
    if args.talk_test:
        return talk_test(args.talk_test)

    import winapi as wa
    if args.quit:
        return 0 if signal_running(WM_APP_QUIT, args.only_from) else 1
    if args.toggle:
        return 0 if signal_running(WM_APP_TOGGLE, args.only_from) else 1
    if args.wav:
        args.wav = os.path.abspath(args.wav)

    wa.set_dpi_awareness()
    _takeover = os.path.join(config.ROOT_DIR, "build", ".takeover")
    if os.path.exists(_takeover):
        try:
            os.remove(_takeover)
        except OSError:
            pass
        signal_running(WM_APP_QUIT)  # закрыть прежнюю копию, затем занять её место
    mutex = acquire_single_instance()
    if mutex is None:
        log.info("already running")
        wa.message_box(f"{config.APP_NAME} уже запущен — значок в трее.\n"
                       "Кликните в поле ввода и нажмите Ctrl+Space.", config.APP_NAME)
        return 0

    try:
        app = App(args)
    except Exception as e:  # noqa: BLE001
        log.exception("startup failed")
        wa.message_box(f"Не удалось запустить {config.APP_NAME}:\n{e}\n\n"
                       f"Подробности: {os.path.join(config.LOG_DIR, 'app.log')}",
                       config.APP_NAME, wa.MB_OK | wa.MB_ICONERROR)
        return 1
    if args.console:
        import signal
        signal.signal(signal.SIGINT, lambda *a: app.post_quit())
        app.overlay.keepalive()
    try:
        app.overlay.run_loop()
    finally:
        wa.CloseHandle(mutex)
        log.info("bye")
    return 0


if __name__ == "__main__":
    code = main()
    # Жёсткий выход: не ждём фоновых потоков (PortAudio, Vosk, pystray).
    logging.shutdown()
    try:
        sys.stdout.flush()
    except Exception:  # noqa: BLE001
        pass
    os._exit(code)
