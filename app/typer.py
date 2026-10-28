"""Ввод текста в активное окно.

clipboard (по умолчанию) — текст кладётся в буфер обмена и вставляется Ctrl+V,
    после чего прежнее содержимое буфера (все форматы) возвращается на место.
    Текст отдаётся через «отложенную отрисовку» (delayed rendering): так видно,
    когда приложение забрало текст, и буфер не восстанавливается раньше времени.
    В журнал буфера обмена (Win+V) продиктованный текст не попадает.
unicode — посимвольный ввод через SendInput(KEYEVENTF_UNICODE). Быстрее
    не бывает, но часть программ (например, новый Блокнот Windows 11)
    искажает такой ввод — поэтому это запасной вариант.
"""
from __future__ import annotations

import ctypes
import logging
import queue
import threading
import time
from ctypes import wintypes as W

import winapi as wa

log = logging.getLogger("typer")

MapVirtualKeyW = wa._fn(wa.user32, "MapVirtualKeyW", W.UINT, W.UINT, W.UINT)

_MOD_VK = {"ctrl": wa.VK_CONTROL, "control": wa.VK_CONTROL, "shift": wa.VK_SHIFT,
           "alt": wa.VK_MENU, "win": wa.VK_LWIN}
_KEY_VK = {"v": wa.VK_V, "insert": wa.VK_INSERT, "ins": wa.VK_INSERT,
           "enter": wa.VK_RETURN, "return": wa.VK_RETURN}


# ------------------------------------------------------------------ SendInput
def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> wa.INPUT:
    inp = wa.INPUT()
    inp.type = wa.INPUT_KEYBOARD
    inp.ki = wa.KEYBDINPUT(vk, scan, flags, 0, 0)
    return inp


def _vk(vk: int, up: bool = False) -> wa.INPUT:
    flags = wa.KEYEVENTF_KEYUP if up else 0
    if vk in wa.EXTENDED_VKS:
        flags |= wa.KEYEVENTF_EXTENDEDKEY
    return _key(vk, MapVirtualKeyW(vk, 0), flags)


def _send(events: list) -> int:
    if not events:
        return 0
    arr = (wa.INPUT * len(events))(*events)
    n = wa.SendInput(len(events), arr, ctypes.sizeof(wa.INPUT))
    if n != len(events):
        log.warning("SendInput inserted %s of %s events (err %s)", n, len(events),
                    ctypes.get_last_error())
    return n


def send_combo(spec: str) -> None:
    """'ctrl+v', 'shift+insert', 'enter' ..."""
    parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    mods = [_MOD_VK[p] for p in parts[:-1] if p in _MOD_VK]
    key = _KEY_VK.get(parts[-1]) if parts else None
    if key is None:
        key = wa.VK_V
    ev = [_vk(m) for m in mods] + [_vk(key), _vk(key, up=True)]
    ev += [_vk(m, up=True) for m in reversed(mods)]
    _send(ev)


def send_unicode(text: str, delay: float = 0.004) -> None:
    """Посимвольно, с паузой: пачкой SendInput многие программы путают символы."""
    data = text.encode("utf-16-le")
    units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
    i = 0
    while i < len(units):
        n = 2 if 0xD800 <= units[i] <= 0xDBFF and i + 1 < len(units) else 1
        ev = []
        for u in units[i:i + n]:
            ev.append(_key(0, u, wa.KEYEVENTF_UNICODE))
        for u in units[i:i + n]:
            ev.append(_key(0, u, wa.KEYEVENTF_UNICODE | wa.KEYEVENTF_KEYUP))
        _send(ev)
        i += n
        if delay:
            time.sleep(delay)


def send_enter(with_shift: bool) -> None:
    send_combo("shift+enter" if with_shift else "enter")
    time.sleep(0.02)


# ------------------------------------------------------------------ clipboard
# Форматы, которые не являются блоками памяти HGLOBAL (их не сохраняем):
# BITMAP, METAFILEPICT, PALETTE, ENHMETAFILE, OWNERDISPLAY, DSP*.
# Картинки при этом сохраняются через CF_DIB/CF_DIBV5.
_SKIP_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}
_SNAPSHOT_LIMIT = 256 * 1024 * 1024


def _alloc(data: bytes):
    h = wa.GlobalAlloc(wa.GMEM_MOVEABLE, max(1, len(data)))
    if not h:
        return None
    p = wa.GlobalLock(h)
    if not p:
        wa.GlobalFree(h)
        return None
    ctypes.memmove(p, data, len(data))
    wa.GlobalUnlock(h)
    return h


def _set_data(fmt: int, data: bytes) -> None:
    h = _alloc(data)
    if h and not wa.SetClipboardData(fmt, h):
        wa.GlobalFree(h)


class ClipboardPaster:
    """Вставка через буфер обмена. owner_hwnd — окно, чей поток постоянно
    обрабатывает сообщения: туда приходят WM_RENDERFORMAT и т.п.
    on_message() надо вызывать из оконной процедуры этого окна."""

    def __init__(self, owner_hwnd: int):
        self.hwnd = owner_hwnd
        self._pending: bytes | None = None
        self._rendered = threading.Event()
        self.cf_history = wa.RegisterClipboardFormatW("CanIncludeInClipboardHistory")
        self.cf_cloud = wa.RegisterClipboardFormatW("CanUploadToCloudClipboard")
        self.cf_exclude = wa.RegisterClipboardFormatW(
            "ExcludeClipboardContentFromMonitorProcessing")

    # ---------------------------------------------------- поток окна-владельца
    def on_message(self, msg: int, wp: int, lp: int):
        if msg == wa.WM_RENDERFORMAT:
            data = self._pending
            if wp == wa.CF_UNICODETEXT and data is not None:
                _set_data(wa.CF_UNICODETEXT, data)   # OpenClipboard здесь не нужен
                self._rendered.set()
            return 0
        if msg == wa.WM_RENDERALLFORMATS:
            data = self._pending
            if data is not None and wa.OpenClipboard(self.hwnd):
                try:
                    if wa.GetClipboardOwner() == self.hwnd:
                        _set_data(wa.CF_UNICODETEXT, data)
                finally:
                    wa.CloseClipboard()
            return 0
        if msg == wa.WM_DESTROYCLIPBOARD:
            return 0
        return None

    # --------------------------------------------------------- рабочий поток
    def _open(self) -> bool:
        for _ in range(50):
            if wa.OpenClipboard(self.hwnd):
                return True
            time.sleep(0.02)
        return False

    def snapshot(self):
        """Все форматы буфера как [(формат, байты)], None — если буфер занят."""
        if not self._open():
            return None
        items, total = [], 0
        try:
            fmt = 0
            while True:
                fmt = wa.EnumClipboardFormats(fmt)
                if not fmt:
                    break
                if fmt in _SKIP_FORMATS or 0x0200 <= fmt <= 0x03FF:
                    continue
                h = wa.GetClipboardData(fmt)
                if not h:
                    continue
                size = wa.GlobalSize(h)
                if not size or total + size > _SNAPSHOT_LIMIT:
                    continue
                p = wa.GlobalLock(h)
                if not p:
                    continue
                try:
                    items.append((fmt, ctypes.string_at(p, size)))
                    total += size
                finally:
                    wa.GlobalUnlock(h)
        finally:
            wa.CloseClipboard()
        log.debug("clipboard snapshot: %s", [(f, len(d)) for f, d in items])
        return items

    def _set_private_flags(self, skip=()) -> None:
        """Не сохранять в журнал Win+V, не синхронизировать, не трогать менеджерам буфера."""
        for fmt in (self.cf_history, self.cf_cloud, self.cf_exclude):
            if fmt and fmt not in skip:
                _set_data(fmt, b"\0\0\0\0")

    def restore(self, items) -> None:
        if items is None:
            return
        if not self._open():
            log.warning("clipboard busy: previous content not restored")
            return
        try:
            wa.EmptyClipboard()
            for fmt, data in items:
                _set_data(fmt, data)
            if items:  # содержимое уже есть в журнале — не дублируем
                self._set_private_flags(skip={f for f, _ in items})
        finally:
            wa.CloseClipboard()
        log.debug("clipboard restored: %d formats", len(items))

    def paste(self, text: str, keys: str = "ctrl+v") -> bool:
        data = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-16-le") + b"\0\0"
        saved = self.snapshot()
        self._rendered.clear()
        self._pending = data
        if not self._open():
            self._pending = None
            log.warning("clipboard busy: falling back to unicode typing")
            return False
        try:
            wa.EmptyClipboard()
            wa.SetClipboardData(wa.CF_UNICODETEXT, None)   # отдадим по запросу
            self._set_private_flags()
        finally:
            wa.CloseClipboard()
        time.sleep(0.03)
        early = self._rendered.is_set()   # текст уже забрал какой-то монитор буфера
        send_combo(keys)
        if early:
            log.debug("text was rendered before paste (clipboard monitor)")
            time.sleep(0.6)
        elif self._rendered.wait(2.5):
            time.sleep(0.15)             # приложение дочитывает буфер
        else:
            log.info("target window did not request the text")
        self._pending = None
        self.restore(saved)
        return True


# ---------------------------------------------------------------------- thread
class Typer(threading.Thread):
    """Очередь текстов на ввод. Печатает только когда отпущены Ctrl/Alt/Shift/Win,
    иначе вставка/символы превратятся в другие сочетания клавиш."""

    def __init__(self, get_cfg):
        super().__init__(daemon=True, name="typer")
        self.q: queue.Queue[str | None] = queue.Queue()
        self.get_cfg = get_cfg
        self.paster: ClipboardPaster | None = None
        self.on_typed = None  # callback(text)

    def type_text(self, text: str) -> None:
        if text:
            self.q.put(text)

    def stop(self) -> None:
        self.q.put(None)

    def run(self) -> None:
        while True:
            text = self.q.get()
            if text is None:
                return
            try:
                self._type(text)
            except Exception:  # noqa: BLE001
                log.exception("typing failed")

    def method_for_foreground(self, cfg: dict) -> str:
        method = str(cfg.get("typing_method", "clipboard")).lower()
        per_app = cfg.get("per_app_typing") or {}
        if isinstance(per_app, dict) and per_app:
            exe = wa.foreground_process_name()
            for name, m in per_app.items():
                if str(name).lower() == exe:
                    method = str(m).lower()
                    break
        return method

    def _type(self, text: str) -> None:
        t0 = time.monotonic()
        while wa.modifiers_down() and time.monotonic() - t0 < 6.0:
            time.sleep(0.02)
        cfg = self.get_cfg()
        method = self.method_for_foreground(cfg)
        if method != "unicode" and self.paster is not None:
            if self.paster.paste(text, str(cfg.get("paste_keys", "ctrl+v"))):
                if self.on_typed:
                    self.on_typed(text)
                return
        shift_enter = str(cfg.get("newline_key", "shift+enter")).lower() != "enter"
        for i, seg in enumerate(text.split("\n")):
            if i:
                send_enter(shift_enter)
            if seg:
                send_unicode(seg)
        if self.on_typed:
            self.on_typed(text)
