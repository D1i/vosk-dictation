"""Запись разговора в текстовый лог с подписью реплик никами.

Что делает:
  * пишет звук, который слышно из динамиков (все собеседники в Discord) —
    системный loopback через библиотеку soundcard;
  * отдельно пишет микрофон (твой голос);
  * распознаёт обе дорожки Vosk отдельно (эхо не мешает: твой голос в динамики
    не возвращается);
  * реплики собеседников подписывает никами по данным Discord (кто когда говорил),
    твои — твоим ником; без Discord: «Собеседник» и «Я».

Логи: logs/talks/<дата>_<канал>.txt, строки вида [ЧЧ:ММ:СС] Ник: текст.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import threading
import time

import warnings

import config
from diarize import LogWriter, SpeakerTimeline

log = logging.getLogger("recorder")
# soundcard периодически предупреждает о разрывах буфера — на распознавание не влияет
warnings.filterwarnings("ignore", message="data discontinuity in recording")

RATE = 16000
BLOCK = 3200  # 0.2 c


def talks_dir() -> str:
    d = os.path.join(config.LOG_DIR, "talks")
    os.makedirs(d, exist_ok=True)
    return d


def _safe(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_()" else "_" for c in (name or ""))
    return keep.strip().strip(".") or "discord"


class _Track(threading.Thread):
    """Одна звуковая дорожка: захват -> Vosk -> строки лога с привязкой к говорящему."""

    def __init__(self, name: str, source, model, timeline: SpeakerTimeline,
                 writer: LogWriter, attribute, log_text: bool):
        super().__init__(daemon=True, name=f"track-{name}")
        self.name = name
        self.source = source          # объект с open()/read()->bytes|None/close(), .rate
        self.model = model
        self.timeline = timeline
        self.writer = writer
        self.attribute = attribute    # (start, end) -> ник
        self.log_text = log_text
        self._stopev = threading.Event()
        self.t0 = None
        self.error: str | None = None

    def stop(self) -> None:
        self._stopev.set()

    def run(self) -> None:
        try:
            self._run()
        except Exception as e:  # noqa: BLE001
            self.error = str(e) or e.__class__.__name__
            log.exception("track %s failed", self.name)

    def _run(self) -> None:
        from vosk import KaldiRecognizer
        self.source.open()
        rate = self.source.rate
        rec = KaldiRecognizer(self.model, rate)
        rec.SetWords(True)
        self.t0 = time.monotonic()
        fed = 0  # сколько сэмплов отдано распознавателю
        while not self._stopev.is_set():
            data = self.source.read()
            if data is None:
                break
            if not data:
                continue
            if rec.AcceptWaveform(data):
                self._emit(json.loads(rec.Result()), rate, fed)
            fed += len(data) // 2
        self._emit(json.loads(rec.FinalResult()), rate, fed)

    def _emit(self, result: dict, rate: int, fed: int) -> None:
        text = result.get("text", "").strip()
        if not text:
            return
        words = result.get("result") or []
        if words:
            start = self.t0 + float(words[0]["start"])
            end = self.t0 + float(words[-1]["end"])
        else:
            now = time.monotonic()
            start, end = now - 2.0, now
        speaker = self.attribute(start, end)
        clock = datetime.datetime.now().strftime("%H:%M:%S")
        if self.log_text:
            log.info("[%s] %s: %s", self.name, speaker, text)
        self.writer.write(speaker, text, clock, end)


# ------------------------------------------------------------------ sources
class LoopbackSource:
    """Системный звук из динамиков через soundcard (WASAPI loopback)."""

    def __init__(self, device_name: str | None = None):
        self.device_name = device_name
        self.rate = RATE
        self._rec = None
        self._ctx = None
        self.name = ""

    def open(self) -> None:
        import soundcard as sc
        if self.device_name:
            spk = next((s for s in sc.all_speakers()
                        if self.device_name.lower() in s.name.lower()), None) \
                or sc.default_speaker()
        else:
            spk = sc.default_speaker()
        mic = sc.get_microphone(spk.name, include_loopback=True)
        self.name = spk.name
        self._ctx = mic.recorder(samplerate=self.rate, channels=1, blocksize=BLOCK)
        self._rec = self._ctx.__enter__()
        log.info("loopback opened: %s", self.name)

    def read(self) -> bytes | None:
        import numpy as np
        if self._rec is None:
            return None
        data = self._rec.record(numframes=BLOCK)  # float32 [-1,1], (frames, ch)
        mono = data[:, 0] if data.ndim > 1 else data
        return (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

    def close(self) -> None:
        try:
            if self._ctx is not None:
                self._ctx.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        self._rec = self._ctx = None


class MicSource:
    """Микрофон через soundcard (твой голос)."""

    def __init__(self, device_name: str | None = None):
        self.device_name = device_name
        self.rate = RATE
        self._rec = None
        self._ctx = None
        self.name = ""

    def open(self) -> None:
        import soundcard as sc
        mic = None
        if self.device_name:
            mic = next((m for m in sc.all_microphones()
                        if self.device_name.lower() in m.name.lower()), None)
        mic = mic or sc.default_microphone()
        self.name = mic.name
        self._ctx = mic.recorder(samplerate=self.rate, channels=1, blocksize=BLOCK)
        self._rec = self._ctx.__enter__()
        log.info("mic opened: %s", self.name)

    def read(self) -> bytes | None:
        import numpy as np
        if self._rec is None:
            return None
        data = self._rec.record(numframes=BLOCK)
        mono = data[:, 0] if data.ndim > 1 else data
        return (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

    def close(self) -> None:
        try:
            if self._ctx is not None:
                self._ctx.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        self._rec = self._ctx = None


# ----------------------------------------------------------------- recorder
class Recorder:
    """Одна сессия записи разговора. Управляется из главного потока."""

    def __init__(self, models, cfg: dict, on_state=None):
        self.models = models
        self.cfg = cfg
        self.on_state = on_state or (lambda text: None)
        self.timeline = SpeakerTimeline()
        self.writer: LogWriter | None = None
        self.tracks: list[_Track] = []
        self.self_ids: set[str] = set()
        self.self_nick = "Я"
        self.other_fallback = "Собеседник"
        self.channel_id: str | None = None
        self.channel_name: str | None = None
        self.active = False
        self.path: str | None = None
        self._names_single: dict[str, str] = {}

    # --- привязка ---------------------------------------------------------
    def _attr_others(self, start: float, end: float) -> str:
        uid, nick = self.timeline.speaker_for(start, end, exclude=self.self_ids)
        if nick:
            return nick
        # если в канале ровно один собеседник — подписываем им
        others = {u: n for u, n in self._names_single.items() if u not in self.self_ids}
        if len(others) == 1:
            return next(iter(others.values()))
        return self.other_fallback

    def _attr_self(self, start: float, end: float) -> str:
        return self.self_nick

    # --- данные от Discord RPC -------------------------------------------
    def set_self(self, user_id: str | None, nick: str | None) -> None:
        if user_id:
            self.self_ids.add(str(user_id))
        if nick:
            self.self_nick = nick

    def on_voice_channel(self, channel_id, names: dict, merge: bool = False,
                         channel_name: str | None = None) -> None:
        if not merge:
            self.channel_id = channel_id
            self._names_single = dict(names)
            if channel_name:
                self.channel_name = channel_name
        else:
            self._names_single.update(names)
        self.timeline.set_names(names)

    def on_speaking(self, user_id: str, speaking: bool, t: float) -> None:
        if speaking:
            self.timeline.start(user_id, t)
        else:
            self.timeline.stop(user_id, t)

    # --- запуск/остановка -------------------------------------------------
    def start(self, channel_name: str | None = None) -> None:
        if self.active:
            return
        self.models.ready.wait()
        if self.models.model is None:
            raise RuntimeError("модель Vosk не загружена")
        os.makedirs(talks_dir(), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        label = _safe(channel_name or self.channel_id or "talk")
        self.path = os.path.join(talks_dir(), f"{stamp}_{label}.txt")
        self.writer = LogWriter(self.path, merge_gap_sec=float(
            self.cfg.get("talk_merge_gap_sec", 6) or 0))
        note = self.cfg.get("talk_header",
                            "# Запись разговора. Предупредите собеседников о записи.\n")
        self.writer.open(f"{note}# {datetime.datetime.now():%Y-%m-%d %H:%M}\n\n")
        log_text = bool(self.cfg.get("log_text", False))
        self.tracks = []
        errors = []
        # дорожка собеседников (динамики)
        try:
            loop = LoopbackSource(self.cfg.get("talk_output_device"))
            self.tracks.append(_Track("loopback", loop, self.models.model,
                                      self.timeline, self.writer, self._attr_others, log_text))
        except Exception as e:  # noqa: BLE001
            errors.append(f"динамики: {e}")
        # дорожка микрофона
        if self.cfg.get("talk_record_mic", True):
            mic = MicSource(self.cfg.get("talk_input_device"))
            self.tracks.append(_Track("mic", mic, self.models.model,
                                      self.timeline, self.writer, self._attr_self, log_text))
        for t in self.tracks:
            t.start()
        self.active = True
        self.on_state("Запись разговора идёт")
        log.info("recording started -> %s", self.path)
        if errors:
            log.warning("track problems: %s", "; ".join(errors))

    def stop(self) -> None:
        if not self.active:
            return
        self.active = False
        for t in self.tracks:
            t.stop()
        for t in self.tracks:
            t.join(timeout=5.0)
        errs = [t.error for t in self.tracks if t.error]
        if self.writer is not None:
            self.writer.close(f"\n# Конец записи {datetime.datetime.now():%H:%M}\n")
        self.tracks = []
        self.on_state("Запись остановлена")
        log.info("recording stopped: %s", self.path)
        if errs:
            raise RuntimeError("; ".join(errs))
