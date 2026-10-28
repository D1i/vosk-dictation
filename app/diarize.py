"""Привязка распознанных реплик к говорящему (диаризация по данным Discord RPC).

Идея: Discord сообщает интервалы речи каждого участника (кто и когда говорил),
а Vosk даёт фразы со временем слов. Каждой фразе назначаем ник того, чья речь
сильнее всего пересекается с ней по времени. Всё время — в секундах monotonic.
Модуль не зависит от Windows и тестируется отдельно.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class _Interval:
    start: float
    end: float | None  # None — ещё говорит


class SpeakerTimeline:
    """Потокобезопасно копит интервалы речи по user_id и карту user_id -> ник."""

    def __init__(self, keep_sec: float = 900.0):
        self.keep_sec = keep_sec
        self._lock = threading.Lock()
        self._open: dict[str, float] = {}                 # user_id -> начало текущей речи
        self._done: dict[str, list[_Interval]] = {}       # user_id -> закрытые интервалы
        self._names: dict[str, str] = {}                  # user_id -> ник

    # --- обновления от RPC ------------------------------------------------
    def set_name(self, user_id: str, nick: str) -> None:
        if user_id and nick:
            with self._lock:
                self._names[str(user_id)] = nick

    def set_names(self, mapping: dict[str, str]) -> None:
        with self._lock:
            for uid, nick in mapping.items():
                if uid and nick:
                    self._names[str(uid)] = nick

    def name_of(self, user_id: str) -> str | None:
        with self._lock:
            return self._names.get(str(user_id))

    def start(self, user_id: str, t: float) -> None:
        user_id = str(user_id)
        with self._lock:
            self._open.setdefault(user_id, t)

    def stop(self, user_id: str, t: float) -> None:
        user_id = str(user_id)
        with self._lock:
            s = self._open.pop(user_id, None)
            if s is None:
                return
            self._done.setdefault(user_id, []).append(_Interval(s, t))
            self._prune(t)

    def _prune(self, now: float) -> None:
        cutoff = now - self.keep_sec
        for uid, lst in list(self._done.items()):
            lst[:] = [iv for iv in lst if (iv.end or now) >= cutoff]
            if not lst:
                self._done.pop(uid, None)

    # --- запрос -----------------------------------------------------------
    def overlaps(self, start: float, end: float) -> dict[str, float]:
        """Сколько секунд каждый говорил в интервале [start, end]."""
        if end < start:
            start, end = end, start
        res: dict[str, float] = {}
        with self._lock:
            for uid, lst in self._done.items():
                total = 0.0
                for iv in lst:
                    e = iv.end if iv.end is not None else end
                    total += max(0.0, min(end, e) - max(start, iv.start))
                if total > 0:
                    res[uid] = total
            for uid, s in self._open.items():  # ещё открытые интервалы
                total = max(0.0, end - max(start, s))
                if total > 0:
                    res[uid] = res.get(uid, 0.0) + total
        return res

    def speaker_for(self, start: float, end: float,
                    exclude: set[str] | None = None) -> tuple[str | None, str | None]:
        """Возвращает (user_id, ник) того, кто говорил больше всех в интервале."""
        ov = self.overlaps(start, end)
        if exclude:
            ov = {u: v for u, v in ov.items() if u not in exclude}
        if not ov:
            return None, None
        uid = max(ov, key=ov.get)
        with self._lock:
            return uid, self._names.get(uid)


@dataclass
class LogWriter:
    """Пишет реплики в файл: [ЧЧ:ММ:СС] Ник: текст. Склеивает подряд идущие
    реплики одного человека в один абзац, если между ними мало времени."""
    path: str
    merge_gap_sec: float = 6.0
    _fh: object = field(default=None, repr=False)
    _last_speaker: str | None = field(default=None, repr=False)
    _last_time: float = field(default=0.0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def open(self, header: str = "") -> None:
        self._fh = open(self.path, "a", encoding="utf-8")
        if header:
            self._fh.write(header)
            self._fh.flush()

    def write(self, speaker: str, text: str, clock: str, now: float) -> None:
        text = text.strip()
        if not text or self._fh is None:
            return
        with self._lock:
            same = (speaker == self._last_speaker and now - self._last_time <= self.merge_gap_sec)
            if same:
                self._fh.write(" " + text)
            else:
                if self._last_speaker is not None:
                    self._fh.write("\n")
                self._fh.write(f"[{clock}] {speaker}: {text}")
            self._fh.flush()
            self._last_speaker = speaker
            self._last_time = now

    def close(self, footer: str = "") -> None:
        with self._lock:
            if self._fh is not None:
                if self._last_speaker is not None:
                    self._fh.write("\n")
                if footer:
                    self._fh.write(footer)
                self._fh.close()
                self._fh = None
