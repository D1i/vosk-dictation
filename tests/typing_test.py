"""Проверка способов ввода текста в активное окно (для отладки).

Запуск: tests\\typing_test.bat, затем за 4 секунды кликнуть в окно (например, Блокнот).
В окно печатается по строке на способ; журнал — logs\\typing_test.log
(там же — восстановился ли буфер обмена после вставки).
"""
import ctypes
import logging
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import winapi as wa  # noqa: E402
import typer  # noqa: E402

os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
logging.basicConfig(filename=os.path.join(ROOT, "logs", "typing_test.log"), level=logging.DEBUG,
                    format="%(asctime)s %(name)s: %(message)s", encoding="utf-8")
log = logging.getLogger("typing_test")

TEXT = "Съешь же ещё этих мягких французских булок, да выпей чаю 0123456789"
ORIGINAL = "ORIGINAL clipboard текст ✓"


def read_text(paster):
    if not paster._open():
        return None
    try:
        h = wa.GetClipboardData(wa.CF_UNICODETEXT)
        if not h:
            return None
        p = wa.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            wa.GlobalUnlock(h)
    finally:
        wa.CloseClipboard()


def check(paster, cf_custom, where):
    text = read_text(paster)
    custom = False
    if paster._open():
        try:
            custom = bool(wa.GetClipboardData(cf_custom))
        finally:
            wa.CloseClipboard()
    ok = text == ORIGINAL and custom
    log.info("[%s] clipboard %s: text=%r custom=%s", where, "OK" if ok else "CHANGED", text, custom)
    return ok


def worker(paster, hwnd, only):
    try:
        time.sleep(4)
        target = wa.foreground_process_name()
        log.info("target: %s", target)
        cf_custom = wa.RegisterClipboardFormatW("VoskDictationTest")
        # исходный буфер: текст + свой формат
        if paster._open():
            try:
                wa.EmptyClipboard()
                typer._set_data(wa.CF_UNICODETEXT, (ORIGINAL + "\0").encode("utf-16-le"))
                typer._set_data(cf_custom, b"custom-bytes")
            finally:
                wa.CloseClipboard()
        check(paster, cf_custom, "start")
        modes = [
            ("unicode", lambda t: typer.send_unicode(t)),
            ("clip", lambda t: paster.paste(t)),
            ("clip-multiline", lambda t: paster.paste(t + "\nвторая строка")),
        ]
        for name, fn in modes:
            if only and name not in only:
                continue
            if wa.foreground_process_name() != target:
                log.info("focus changed -> stop")
                break
            paster.paste(f"{name}: ")
            check(paster, cf_custom, f"after label {name}")
            t0 = time.perf_counter()
            fn(TEXT)
            log.info("%s took %.0f ms", name, (time.perf_counter() - t0) * 1000)
            check(paster, cf_custom, f"after {name}")
            time.sleep(0.4)
            paster.paste("\n")
            time.sleep(0.2)
        time.sleep(1.0)
        check(paster, cf_custom, "end")
        log.info("done")
    except Exception:  # noqa: BLE001
        log.exception("worker failed")
    finally:
        wa.PostMessageW(hwnd, wa.WM_CLOSE, 0, 0)


def main():
    only = sys.argv[1:]
    paster_box = {}

    def wndproc(hwnd, msg, wp, lp):
        p = paster_box.get("p")
        if p is not None:
            r = p.on_message(msg, wp, lp)
            if r is not None:
                return r
        if msg == wa.WM_CLOSE:
            wa.DestroyWindow(hwnd)
            return 0
        if msg == wa.WM_DESTROY:
            wa.PostQuitMessage(0)
            return 0
        return wa.DefWindowProcW(hwnd, msg, wp, lp)

    proc = wa.WNDPROC(wndproc)
    wc = wa.WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(wa.WNDCLASSEXW)
    wc.lpfnWndProc = proc
    wc.hInstance = wa.GetModuleHandleW(None)
    wc.lpszClassName = "VoskTypingTest"
    wa.RegisterClassExW(ctypes.byref(wc))
    hwnd = wa.CreateWindowExW(0, "VoskTypingTest", None, 0, 0, 0, 0, 0,
                              wa.HWND_MESSAGE, None, wc.hInstance, None)
    paster = typer.ClipboardPaster(hwnd)
    paster_box["p"] = paster
    threading.Thread(target=worker, args=(paster, hwnd, only), daemon=True).start()
    msg = wa.MSG()
    while wa.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        wa.TranslateMessage(ctypes.byref(msg))
        wa.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    main()
    logging.shutdown()
    os._exit(0)
