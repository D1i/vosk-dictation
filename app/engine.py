"""Захват звука и распознавание речи Vosk (без привязки к UI)."""
from __future__ import annotations

import array
import itertools
import json
import logging
import math
import os
import queue
import threading
import time
import wave

log = logging.getLogger("engine")


# ------------------------------------------------------------------- model
def ensure_model_extracted(model_path: str) -> None:
    """Если папка модели неполная, но рядом (в Downloads или в models/) лежит
    архив <имя>.zip — распаковать его на месте, быстрым диском Windows.
    Полностью распакованную модель не трогает; ошибки не фатальны."""
    import os as _os, zipfile as _zip
    def _complete(d):
        return (_os.path.isfile(_os.path.join(d, "am", "final.mdl"))
                and _os.path.isdir(_os.path.join(d, "conf"))
                and (_os.path.isfile(_os.path.join(d, "graph", "HCLG.fst"))
                     or _os.path.isfile(_os.path.join(d, "graph", "HCLr.fst"))))
    try:
        if _complete(model_path):
            return
        name = _os.path.basename(model_path.rstrip("/\\"))
        models_root = _os.path.dirname(model_path)
        home = _os.path.expanduser("~")
        cands = [_os.path.join(home, "Downloads", name + ".zip"),
                 _os.path.join(models_root, name + ".zip")]
        zpath = next((z for z in cands if _os.path.isfile(z)), None)
        if not zpath:
            return
        log.info("распаковываю модель %s из %s ...", name, zpath)
        t0 = time.monotonic()
        with _zip.ZipFile(zpath) as zf:
            zf.extractall(models_root)
        log.info("модель %s распакована за %.0f c", name, time.monotonic() - t0)
    except Exception:  # noqa: BLE001
        log.exception("не удалось распаковать модель %s", model_path)


def _disable_heavy_rescore(model_path: str) -> None:
    """Быстрый режим большой модели: отключаем тяжёлое пере-взвешивание
    (rescore/G.carpa ~1.7 ГБ + rnnlm ~0.6 ГБ). Для диктовки в реальном
    времени оно грузится минутами и добавляет задержку; точность по
    быстрой речи даёт акустическая модель и граф. Папки не удаляем —
    переименовываем (можно вернуть, убрав .disabled)."""
    import os as _os
    for sub in ("rescore", "rnnlm"):
        src = _os.path.join(model_path, sub)
        dst = src + ".disabled"
        if _os.path.isdir(src) and not _os.path.isdir(dst):
            for _ in range(20):
                try:
                    _os.rename(src, dst)
                    log.info("отключил %s (быстрый режим большой модели)", sub)
                    break
                except OSError:
                    time.sleep(0.5)


class ModelHolder:
    """Грузит модель в фоне; аудио до окончания загрузки просто копится."""

    def __init__(self, path: str):
        self.path = path
        self.model = None
        self.error: str | None = None
        self.ready = threading.Event()

    def load_async(self, on_done=None) -> None:
        threading.Thread(target=self._load, args=(on_done,), daemon=True,
                         name="model-loader").start()

    def load(self) -> None:
        self._load(None)

    def _load(self, on_done) -> None:
        t0 = time.monotonic()
        try:
            ensure_model_extracted(self.path)
            _disable_heavy_rescore(self.path)
            if not os.path.isfile(os.path.join(self.path, "am", "final.mdl")):
                raise FileNotFoundError(f"модель не найдена: {self.path}")
            import vosk
            vosk.SetLogLevel(-1)
            parent, name = os.path.split(self.path)
            if not self.path.isascii() and name.isascii():
                # Vosk (fopen) не открывает пути с кириллицей в Windows —
                # переходим в родительскую папку и передаём относительный путь.
                prev = os.getcwd()
                os.chdir(parent)
                try:
                    self.model = vosk.Model(name)
                finally:
                    os.chdir(prev)
            else:
                self.model = vosk.Model(self.path)
            log.info("model loaded in %.1fs: %s", time.monotonic() - t0, self.path)
        except Exception as e:  # noqa: BLE001
            self.error = str(e) or e.__class__.__name__
            log.exception("model load failed")
        finally:
            self.ready.set()
            if on_done:
                on_done()


# ------------------------------------------------------------------- audio
def level_of(data: bytes) -> float:
    """Громкость блока int16 в диапазоне 0..1 (логарифмическая шкала)."""
    a = array.array("h")
    a.frombytes(data[: len(data) // 2 * 2])
    if not a:
        return 0.0
    sub = a[::4]
    rms = math.sqrt(sum(x * x for x in sub) / len(sub)) / 32768.0
    if rms <= 1e-6:
        return 0.0
    db = 20 * math.log10(rms)          # тишина ~ -60..-50, речь ~ -30..-10
    return max(0.0, min(1.0, (db + 52) / 36))


def resolve_device(spec):
    """None -> устройство по умолчанию; int -> индекс; str -> часть названия."""
    if spec is None or spec == "":
        return None
    if isinstance(spec, int):
        return spec
    import sounddevice as sd
    want = str(spec).lower()
    default_api = sd.default.hostapi
    matches = [(d["hostapi"] != default_api, i) for i, d in enumerate(sd.query_devices())
               if d["max_input_channels"] > 0 and want in d["name"].lower()]
    if not matches:
        log.warning("input device %r not found, using default", spec)
        return None
    return sorted(matches)[0][1]


class MicSource:
    def __init__(self, device, on_data):
        self.device = device
        self.on_data = on_data
        self.rate = 16000
        self.stream = None
        self.name = ""

    def open(self) -> None:
        import sounddevice as sd
        dev = resolve_device(self.device)
        rate = 16000
        try:
            sd.check_input_settings(device=dev, samplerate=rate, channels=1, dtype="int16")
        except Exception:  # noqa: BLE001
            rate = int(sd.query_devices(dev, "input")["default_samplerate"])
        self.rate = rate
        self.name = sd.query_devices(dev, "input")["name"]
        self.stream = sd.RawInputStream(samplerate=rate, blocksize=int(rate * 0.05),
                                        device=dev, channels=1, dtype="int16",
                                        callback=self._cb)
        self.stream.start()
        log.info("mic opened: %s @ %s Hz", self.name, rate)

    def _cb(self, indata, frames, time_info, status):  # поток PortAudio
        if status:
            log.debug("audio status: %s", status)
        self.on_data(bytes(indata))

    def close(self) -> None:
        s, self.stream = self.stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:  # noqa: BLE001
                log.exception("mic close failed")


class WavSource:
    """Подменяет микрофон WAV-файлом (моно, 16 бит) — для проверки без голоса."""

    def __init__(self, path: str, on_data):
        self.path = path
        self.on_data = on_data
        self.rate = 16000
        self._stop = threading.Event()
        self.name = os.path.basename(path)

    def open(self) -> None:
        wf = wave.open(self.path, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError("нужен WAV: моно, 16 бит")
        self.rate = wf.getframerate()
        threading.Thread(target=self._run, args=(wf,), daemon=True, name="wav").start()

    def _run(self, wf) -> None:
        n = int(self.rate * 0.05)
        t_next = time.monotonic()
        with wf:
            while not self._stop.is_set():
                data = wf.readframes(n)
                if not data:
                    data = b"\0\0" * n  # после конца файла — тишина
                self.on_data(data)
                t_next += 0.05
                time.sleep(max(0.0, t_next - time.monotonic()))

    def close(self) -> None:
        self._stop.set()


# ----------------------------------------------------------------- session
_ids = itertools.count(1)


class Session:
    """Одна диктовка: от включения микрофона до выключения.

    callbacks: объект с методами on_partial(session, text), on_final(session, raw, typed),
    on_auto_stop(session), on_ended(session) — вызываются из потока сессии."""

    def __init__(self, models: ModelHolder, formatter, typer, callbacks,
                 auto_stop_sec: float = 0, skip_ms: int = 0, log_text: bool = False,
                 space_after: bool = True):
        self.id = next(_ids)
        self.models = models
        self.formatter = formatter
        self.typer = typer
        self.cb = callbacks
        self.auto_stop_sec = float(auto_stop_sec or 0)
        self.skip_ms = skip_ms
        self.log_text = log_text
        self.space_after = space_after
        self.q: queue.Queue = queue.Queue()
        self.level = 0.0
        self.mic_silent = False   # микрофон отдаёт «цифровой ноль» (нет доступа)
        self.source = None
        self.rate = 16000
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"session-{self.id}")

    # вызывается из UI-потока
    def begin(self, source) -> None:
        self.source = source
        source.open()
        self.rate = source.rate
        self.thread.start()

    def end(self) -> None:
        src, self.source = self.source, None
        if src is not None:
            src.close()
        self.q.put(None)

    # поток источника звука
    def feed(self, data: bytes) -> None:
        self.q.put(data)

    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            self._loop()
        except Exception:  # noqa: BLE001
            log.exception("session failed")
        finally:
            self.level = 0.0
            self.cb.on_ended(self)

    def _loop(self) -> None:
        self.models.ready.wait()
        if self.models.model is None:
            return
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(self.models.model, self.rate)
        skip = int(self.rate * self.skip_ms / 1000) * 2
        zero_bytes = 0            # сколько байт подряд пришло одних нулей с начала
        heard_signal = False
        last_voice = time.monotonic()
        last_partial = ""
        auto_sent = False
        while True:
            try:
                data = self.q.get(timeout=0.2)
            except queue.Empty:
                data = b""
            if data is None:
                break
            now = time.monotonic()
            if data:
                if skip > 0:  # отрезаем звук «бип» в самом начале
                    cut = min(skip, len(data))
                    data, skip = data[cut:], skip - cut
                if data:
                    self.level = level_of(data)
                    if not heard_signal:
                        if data.count(0) == len(data):
                            zero_bytes += len(data)
                            if zero_bytes > self.rate * 2 * 1.5 and not self.mic_silent:
                                self.mic_silent = True
                                log.warning("microphone delivers pure silence (privacy settings?)")
                        else:
                            heard_signal = True
                            self.mic_silent = False
                    if rec.AcceptWaveform(data):
                        text = json.loads(rec.Result()).get("text", "")
                        if text:
                            last_voice = now
                            self._final(text)
                        if last_partial:
                            last_partial = ""
                            self.cb.on_partial(self, "")
                    else:
                        p = json.loads(rec.PartialResult()).get("partial", "")
                        if p:
                            last_voice = now  # фраза ещё идёт
                        if p != last_partial:
                            last_partial = p
                            self.cb.on_partial(self, p)
            if (self.auto_stop_sec > 0 and not auto_sent
                    and now - last_voice > self.auto_stop_sec):
                auto_sent = True
                log.info("auto stop after %.0fs of silence", self.auto_stop_sec)
                self.cb.on_auto_stop(self)
        text = json.loads(rec.FinalResult()).get("text", "")
        if text:
            self._final(text)
        if self.space_after and self.typer is not None:
            tail_text = self.formatter.finish()
            if tail_text:
                self.typer.type_text(tail_text)

    def _final(self, raw: str) -> None:
        typed = self.formatter.feed(raw)
        if self.log_text:
            log.info("recognized: %r -> %r", raw, typed)
        else:
            log.info("recognized %d chars", len(typed))
        if typed and self.typer is not None:
            self.typer.type_text(typed)
        self.cb.on_final(self, raw, typed)
