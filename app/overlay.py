"""Окно-плашка поверх всех окон. Никогда не забирает фокус и пропускает клики:
WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW."""
from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes as W

import winapi as wa
from painter import PAD, Painter, pulse

log = logging.getLogger("overlay")

CLASS_NAME = "VoskDictationOverlay"
TIMER_FRAME = 1
TIMER_KEEPALIVE = 2
FRAME_MS = 40
FADE_IN = 0.12
FADE_OUT = 0.16


class Overlay:
    def __init__(self, on_message, view, title: str = "Vosk Dictation"):
        """on_message(msg, wp, lp) -> int|None — обработчик прикладных сообщений;
        view() -> None | (state, main, dim, hint, level) — что рисовать;
        title — заголовок (не виден; по нему другие копии узнают папку программы)."""
        self.on_message = on_message
        self.view = view
        self.painter = Painter()
        self.hinst = wa.GetModuleHandleW(None)
        self._proc_ref = wa.WNDPROC(self._wndproc)
        wc = wa.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(wa.WNDCLASSEXW)
        wc.lpfnWndProc = self._proc_ref
        wc.hInstance = self.hinst
        wc.lpszClassName = CLASS_NAME
        if not wa.RegisterClassExW(ctypes.byref(wc)):
            raise OSError(f"RegisterClassExW failed: {ctypes.get_last_error()}")
        ex = (wa.WS_EX_LAYERED | wa.WS_EX_TRANSPARENT | wa.WS_EX_TOPMOST
              | wa.WS_EX_TOOLWINDOW | wa.WS_EX_NOACTIVATE)
        self.hwnd = wa.CreateWindowExW(ex, CLASS_NAME, title, wa.WS_POPUP,
                                       0, 0, 0, 0, None, None, self.hinst, None)
        if not self.hwnd:
            raise OSError(f"CreateWindowExW failed: {ctypes.get_last_error()}")
        self.visible = False
        self.scale = 1.0
        self.x = self.y = 0
        self._alpha = 0.0
        self._fade_dir = 0          # +1 появление, -1 исчезание
        self._fade_t0 = 0.0
        self._level = 0.0
        self._memdc = None
        self._hbmp = None
        self._oldbmp = None
        self._bits = None
        self._dib_size = (0, 0)
        self._last_view = None

    # ------------------------------------------------------------- messages
    def _wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == wa.WM_NCHITTEST:
                return wa.HTTRANSPARENT
            if msg == wa.WM_MOUSEACTIVATE:
                return wa.MA_NOACTIVATE
            if msg == wa.WM_TIMER and wp == TIMER_FRAME:
                self._tick()
                return 0
            r = self.on_message(msg, wp, lp)
            if r is not None:
                return r
        except Exception:  # noqa: BLE001
            log.exception("wndproc error (msg=0x%x)", msg)
        return wa.DefWindowProcW(hwnd, msg, wp, lp)

    def post(self, msg: int, wp: int = 0, lp: int = 0) -> None:
        wa.PostMessageW(self.hwnd, msg, wp, lp)

    @staticmethod
    def run_loop() -> None:
        msg = wa.MSG()
        while wa.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            wa.TranslateMessage(ctypes.byref(msg))
            wa.DispatchMessageW(ctypes.byref(msg))

    def keepalive(self, ms: int = 300) -> None:
        """Периодически отдаёт управление Python (нужно для Ctrl+C в консоли)."""
        wa.SetTimer(self.hwnd, TIMER_KEEPALIVE, ms, None)

    # ----------------------------------------------------------- show/hide
    def show(self) -> None:
        if self.visible and self._fade_dir >= 0:
            return
        rc, scale = wa.monitor_for_foreground()
        self.scale = round(scale * 4) / 4 or 1.0
        iw, _ = Painter.size(self.scale)
        self.x = rc.left + (rc.right - rc.left - iw) // 2
        self.y = rc.top + round(max(0, 14 - PAD) * self.scale)
        if not self.visible:
            self._alpha = 0.0
        self._fade_dir = 1
        self._fade_t0 = time.monotonic() - self._alpha * FADE_IN
        self._render()
        wa.SetWindowPos(self.hwnd, wa.HWND_TOPMOST, 0, 0, 0, 0,
                        wa.SWP_NOMOVE | wa.SWP_NOSIZE | wa.SWP_NOACTIVATE)
        wa.ShowWindow(self.hwnd, wa.SW_SHOWNOACTIVATE)
        self.visible = True
        wa.SetTimer(self.hwnd, TIMER_FRAME, FRAME_MS, None)

    def hide(self) -> None:
        if not self.visible or self._fade_dir < 0:
            return
        self._fade_dir = -1
        self._fade_t0 = time.monotonic() - (1.0 - self._alpha) * FADE_OUT

    def _finish_hide(self) -> None:
        wa.KillTimer(self.hwnd, TIMER_FRAME)
        wa.ShowWindow(self.hwnd, wa.SW_HIDE)
        self.visible = False
        self._fade_dir = 0
        self._alpha = 0.0

    # ----------------------------------------------------------- rendering
    def _tick(self) -> None:
        now = time.monotonic()
        if self.view() is None and self._fade_dir >= 0:
            self.hide()
        if self._fade_dir > 0:
            self._alpha = min(1.0, (now - self._fade_t0) / FADE_IN)
        elif self._fade_dir < 0:
            self._alpha = max(0.0, 1.0 - (now - self._fade_t0) / FADE_OUT)
            if self._alpha <= 0.0:
                self._finish_hide()
                return
        self._render()

    def _render(self) -> None:
        v = self.view() or self._last_view
        if v is None:
            return
        self._last_view = v
        state, main, dim, hint, level = v
        # сглаживание уровня: быстро вверх, медленно вниз
        k = 0.6 if level > self._level else 0.25
        self._level += (level - self._level) * k
        shown = max(self._level, pulse(time.monotonic())) if state == "listening" else 0.0
        img = self.painter.render(self.scale, state, main, dim, hint, shown)
        self._push(img, int(255 * self._alpha))

    def _ensure_dib(self, w: int, h: int) -> None:
        if self._dib_size == (w, h) and self._memdc:
            return
        self._free_dib()
        screen = wa.GetDC(None)
        self._memdc = wa.CreateCompatibleDC(screen)
        wa.ReleaseDC(None, screen)
        bmi = wa.BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(wa.BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = wa.BI_RGB
        bits = ctypes.c_void_p()
        self._hbmp = wa.CreateDIBSection(self._memdc, ctypes.byref(bmi), wa.DIB_RGB_COLORS,
                                         ctypes.byref(bits), None, 0)
        if not self._hbmp:
            raise OSError(f"CreateDIBSection failed: {ctypes.get_last_error()}")
        self._oldbmp = wa.SelectObject(self._memdc, self._hbmp)
        self._bits = bits.value
        self._dib_size = (w, h)

    def _free_dib(self) -> None:
        if self._memdc:
            if self._oldbmp:
                wa.SelectObject(self._memdc, self._oldbmp)
            if self._hbmp:
                wa.DeleteObject(self._hbmp)
            wa.DeleteDC(self._memdc)
        self._memdc = self._hbmp = self._oldbmp = self._bits = None
        self._dib_size = (0, 0)

    def _push(self, img, alpha: int) -> None:
        w, h = img.size
        self._ensure_dib(w, h)
        buf = img.tobytes("raw", "BGRa")  # premultiplied BGRA
        ctypes.memmove(self._bits, buf, len(buf))
        screen = wa.GetDC(None)
        try:
            ok = wa.UpdateLayeredWindow(
                self.hwnd, screen, ctypes.byref(W.POINT(self.x, self.y)),
                ctypes.byref(W.SIZE(w, h)), self._memdc, ctypes.byref(W.POINT(0, 0)), 0,
                ctypes.byref(wa.BLENDFUNCTION(wa.AC_SRC_OVER, 0, max(0, min(255, alpha)),
                                              wa.AC_SRC_ALPHA)),
                wa.ULW_ALPHA)
            if not ok:
                log.debug("UpdateLayeredWindow failed: %s", ctypes.get_last_error())
        finally:
            wa.ReleaseDC(None, screen)

    def destroy(self) -> None:
        try:
            wa.KillTimer(self.hwnd, TIMER_FRAME)
            wa.KillTimer(self.hwnd, TIMER_KEEPALIVE)
            self._free_dib()
            wa.DestroyWindow(self.hwnd)
        except Exception:  # noqa: BLE001
            log.exception("destroy failed")
