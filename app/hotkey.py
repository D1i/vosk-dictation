"""Глобальная горячая клавиша: RegisterHotKey, а если комбинация занята —
низкоуровневый хук клавиатуры (WH_KEYBOARD_LL)."""
from __future__ import annotations

import ctypes
import logging

import winapi as wa

log = logging.getLogger("hotkey")

HOTKEY_ID = 0x5D1C

_MODS = {
    "ctrl": wa.MOD_CONTROL, "control": wa.MOD_CONTROL,
    "alt": wa.MOD_ALT,
    "shift": wa.MOD_SHIFT,
    "win": wa.MOD_WIN, "super": wa.MOD_WIN,
}

_KEYS = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B,
    "escape": 0x1B, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "pause": 0x13, "scrolllock": 0x91, "capslock": 0x14,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "`": 0xC0, "~": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC,
}
_KEYS.update({f"f{i}": 0x6F + i for i in range(1, 25)})
_KEYS.update({chr(c): c for c in range(ord("0"), ord("9") + 1)})
_KEYS.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})

_MOD_VKS = {
    wa.MOD_CONTROL: (0x11,),
    wa.MOD_ALT: (0x12,),
    wa.MOD_SHIFT: (0x10,),
    wa.MOD_WIN: (0x5B, 0x5C),
}


def parse(spec: str) -> tuple[int, int]:
    """'ctrl+space' -> (mods, vk). Бросает ValueError."""
    parts = [p.strip().lower() for p in str(spec).replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("пустая горячая клавиша")
    mods = 0
    for p in parts[:-1]:
        if p not in _MODS:
            raise ValueError(f"неизвестный модификатор: {p}")
        mods |= _MODS[p]
    key = parts[-1]
    if key not in _KEYS:
        raise ValueError(f"неизвестная клавиша: {key}")
    return mods, _KEYS[key]


class GlobalHotkey:
    """Регистрирует горячую клавишу для окна hwnd.

    При нажатии окно получает WM_HOTKEY (wParam == HOTKEY_ID) — и в режиме
    RegisterHotKey, и в режиме хука (хук сам шлёт это сообщение), так что
    обработчик один.
    """

    def __init__(self, hwnd: int, hotkey_id: int = HOTKEY_ID):
        self.hwnd = hwnd
        self.id = hotkey_id
        self.mode = None          # "hotkey" | "hook" | None
        self.spec = ""
        self._mods = 0
        self._vk = 0
        self._hook = None
        self._hook_proc = None    # держим ссылку, иначе GC убьёт callback
        self._pressed = False

    # ------------------------------------------------------------------
    def register(self, spec: str) -> str | None:
        """Возвращает None при успехе или текст ошибки."""
        self.unregister()
        try:
            mods, vk = parse(spec)
        except ValueError as e:
            return f"Горячая клавиша «{spec}»: {e}"
        self.spec, self._mods, self._vk = spec, mods, vk
        if wa.RegisterHotKey(self.hwnd, self.id, mods | wa.MOD_NOREPEAT, vk):
            self.mode = "hotkey"
            log.info("hotkey %s registered (RegisterHotKey)", spec)
            return None
        err = ctypes.get_last_error()
        log.warning("RegisterHotKey(%s) failed: %s — using keyboard hook", spec, err)
        return self._install_hook()

    def unregister(self) -> None:
        if self.mode == "hotkey":
            wa.UnregisterHotKey(self.hwnd, self.id)
        elif self.mode == "hook" and self._hook:
            wa.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self.mode = None

    # ------------------------------------------------------------------
    def _mods_match(self) -> bool:
        for flag, vks in _MOD_VKS.items():
            down = any(wa.key_down(v) for v in vks)
            if down != bool(self._mods & flag):
                return False
        return True

    def _install_hook(self) -> str | None:
        def proc(n_code, w_param, l_param):
            try:
                if n_code == wa.HC_ACTION:
                    kb = ctypes.cast(l_param, ctypes.POINTER(wa.KBDLLHOOKSTRUCT)).contents
                    if kb.vkCode == self._vk:
                        if w_param in (wa.WM_KEYDOWN, wa.WM_SYSKEYDOWN):
                            if self._pressed:
                                return 1          # автоповтор — глотаем
                            if self._mods_match():
                                self._pressed = True
                                wa.PostMessageW(self.hwnd, wa.WM_HOTKEY, self.id, 0)
                                return 1
                        elif w_param in (wa.WM_KEYUP, wa.WM_SYSKEYUP) and self._pressed:
                            self._pressed = False
                            return 1
            except Exception:  # noqa: BLE001
                log.exception("hook proc failed")
            return wa.CallNextHookEx(None, n_code, w_param, l_param)

        self._hook_proc = wa.HOOKPROC(proc)
        self._hook = wa.SetWindowsHookExW(wa.WH_KEYBOARD_LL, self._hook_proc,
                                          wa.GetModuleHandleW(None), 0)
        if not self._hook:
            err = ctypes.get_last_error()
            log.error("SetWindowsHookExW failed: %s", err)
            return f"Не удалось назначить горячую клавишу {self.spec} (ошибка {err})"
        self.mode = "hook"
        log.info("hotkey %s registered (keyboard hook)", self.spec)
        return None
