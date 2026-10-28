"""Проверка логики App без Windows: winapi/overlay/hotkey/tray/typer и vosk
подменяются заглушками. Запуск: python tests/test_app_flow.py"""
import importlib.machinery
import importlib.util
import json
import os
import queue
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
sys.path.insert(0, APP)

# ------------------------------------------------------------------ stubs
posted = queue.Queue()

wa = types.ModuleType("winapi")
wa.WM_HOTKEY, wa.WM_CLOSE, wa.WM_DESTROY = 0x0312, 0x0010, 0x0002
wa.WM_RENDERFORMAT, wa.WM_RENDERALLFORMATS, wa.WM_DESTROYCLIPBOARD = 0x0305, 0x0306, 0x0307
wa.PostQuitMessage = lambda code: posted.put(("quit", code))
sys.modules["winapi"] = wa

ov = types.ModuleType("overlay")


class Overlay:
    def __init__(self, on_message, view, title=""):
        self.on_message, self.view, self.hwnd = on_message, view, 1
        self.title = title
        self.visible = False
        self.destroyed = False

    def post(self, msg, wp=0, lp=0):
        posted.put((msg, wp, lp))

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def destroy(self):
        self.destroyed = True

    def keepalive(self, ms=300):
        pass


ov.Overlay = Overlay
ov.CLASS_NAME = "X"
sys.modules["overlay"] = ov

hk = types.ModuleType("hotkey")


class GlobalHotkey:
    def __init__(self, hwnd, hotkey_id=0x5D1C):
        self.spec, self.mode, self.id = "", None, hotkey_id

    def register(self, spec):
        self.spec, self.mode = spec, "hotkey"
        return None

    def unregister(self):
        self.mode = None


hk.GlobalHotkey = GlobalHotkey
sys.modules["hotkey"] = hk

tr = types.ModuleType("tray")


class Tray:
    def __init__(self, app):
        self.listening = []

    def start(self):
        pass

    def set_listening(self, on):
        self.listening.append(on)

    def refresh(self):
        pass

    def notify(self, text):
        pass

    def stop(self):
        pass


tr.Tray = Tray
sys.modules["tray"] = tr

ty = types.ModuleType("typer")


class ClipboardPaster:
    def __init__(self, hwnd):
        self.messages = []

    def on_message(self, msg, wp, lp):
        self.messages.append(msg)
        return 0


class Typer:
    def __init__(self, get_cfg):
        self.out, self.paster = [], None

    def start(self):
        pass

    def type_text(self, t):
        self.out.append(t)

    def stop(self):
        pass


ty.Typer = Typer
ty.ClipboardPaster = ClipboardPaster
sys.modules["typer"] = ty

# fake vosk: «распознаёт» фразы по паузам в тестовом WAV
import engine  # noqa: E402

fake = types.ModuleType("vosk")
PHRASES = ["привет запятая это проверка голосового ввода точка",
           "все работает восклицательный знак"]


class FakeRec:
    def __init__(self, model, rate):
        self.rate, self.speech, self.silence, self.n, self.pending = rate, 0, 0, 0, ""

    def AcceptWaveform(self, data):
        if engine.level_of(data) > 0.25:
            self.speech += len(data)
            self.silence = 0
            return False
        self.silence += len(data)
        if self.speech and self.silence > self.rate * 2 * 0.4:
            self.pending = PHRASES[min(self.n, 1)]
            self.n += 1
            self.speech = 0
            return True
        return False

    def Result(self):
        return json.dumps({"text": self.pending})

    def PartialResult(self):
        return json.dumps({"partial": "привет" if self.speech else ""})

    def FinalResult(self):
        return json.dumps({"text": ""})


fake.KaldiRecognizer = FakeRec
fake.SetLogLevel = lambda x: None
fake.Model = lambda p: object()
sys.modules["vosk"] = fake

# config -> во временную папку
import config  # noqa: E402

tmp = tempfile.mkdtemp()
config.CONFIG_PATH = os.path.join(tmp, "config.json")
config.LOG_DIR = os.path.join(tmp, "logs")
model_dir = os.path.join(tmp, "model")
os.makedirs(os.path.join(model_dir, "am"))
open(os.path.join(model_dir, "am", "final.mdl"), "w").close()
config.DEFAULTS["model_path"] = model_dir
config.DEFAULTS["auto_stop_silence_sec"] = 2
config.DEFAULTS["sounds"] = False

# main.pyw как модуль
loader = importlib.machinery.SourceFileLoader("vd_main", os.path.join(APP, "main.pyw"))
spec = importlib.util.spec_from_loader("vd_main", loader)
main = importlib.util.module_from_spec(spec)
loader.exec_module(main)


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            m = posted.get(timeout=0.05)
        except queue.Empty:
            continue
        if m[0] == "quit":
            return "quit"
        app.on_message(*m)
    return None


def main_test():
    args = types.SimpleNamespace(wav=os.path.join(ROOT, "tests", "test_ru.wav"),
                                 log_text=True, console=False)
    app = main.App(args)
    pump(app, 0.5)                                   # WM_APP_MODEL
    assert app.models.model is not None, app.models.error
    assert app.view() is None

    app.on_message(wa.WM_HOTKEY, 1, 0)               # включить
    assert app.session is not None and app.overlay.visible
    v = app.view()
    assert v[0] == "listening", v
    saw_partial = False
    t0 = time.monotonic()
    while time.monotonic() - t0 < 4:
        pump(app, 0.1)
        v = app.view()
        if v and v[0] == "listening" and not v[2] and "привет" in v[1].lower():
            saw_partial = True
    assert saw_partial, "partial text never shown"
    # ждём авто-выключения по тишине (2 c после конца речи)
    pump(app, 12)
    assert app.session is None, "auto stop did not happen"
    assert not app.overlay.visible
    time.sleep(0.5)
    typed = "".join(app.typer.out)
    print("typed:", repr(typed))
    assert typed == "Привет, это проверка голосового ввода. Все работает! ", typed
    assert app.tray.listening == [True, False], app.tray.listening

    # повторное включение и ручное выключение
    app.typer.out.clear()
    app.on_message(main.WM_APP_TOGGLE, 0, 0)
    assert app.session is not None
    pump(app, 1.0)
    app.on_message(wa.WM_HOTKEY, 1, 0)
    assert app.session is None
    pump(app, 1.0)
    print("second session typed:", app.typer.out)

    # сообщения буфера обмена уходят в ClipboardPaster
    assert app.on_message(wa.WM_RENDERFORMAT, 13, 0) == 0
    assert app.typer.paster.messages == [wa.WM_RENDERFORMAT]

    # заголовок окна содержит папку программы; сравнение папок
    assert app.overlay.title == f"Vosk Dictation|{config.ROOT_DIR}", app.overlay.title
    assert main.same_dir(config.ROOT_DIR, config.ROOT_DIR + os.sep)
    assert not main.same_dir(config.ROOT_DIR, os.path.join(config.ROOT_DIR, "x"))
    assert not main.same_dir("", config.ROOT_DIR)

    # перечитывание настроек и выход
    app.on_message(main.WM_APP_RELOAD, 0, 0)
    app.on_message(main.WM_APP_QUIT, 0, 0)
    assert app.overlay.destroyed
    print("APP FLOW OK")


if __name__ == "__main__":
    main_test()
    os._exit(0)
