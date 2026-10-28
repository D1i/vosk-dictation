"""Минимальные ctypes-обёртки Win32 (корректные для 64-bit)."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes as W

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("winapi доступен только в Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
try:
    shcore = ctypes.WinDLL("shcore", use_last_error=True)
except OSError:  # Windows 7
    shcore = None

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
HCURSOR = W.HANDLE

# ---------------------------------------------------------------- constants
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_TIMER = 0x0113
WM_HOTKEY = 0x0312
WM_NCHITTEST = 0x0084
WM_MOUSEACTIVATE = 0x0021
WM_APP = 0x8000
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

HTTRANSPARENT = -1
MA_NOACTIVATE = 3

WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0
BI_RGB = 0

MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WH_KEYBOARD_LL = 13
HC_ACTION = 0

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_RETURN = 0x0D
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_V = 0x56

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
WM_RENDERFORMAT = 0x0305
WM_RENDERALLFORMATS = 0x0306
WM_DESTROYCLIPBOARD = 0x0307
HWND_MESSAGE = -3

VK_INSERT = 0x2D
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
                0x5B, 0x5C, 0x5D, 0x6F, 0x90, 0xA3, 0xA5}

MB_OK = 0x0
MB_ICONERROR = 0x10
MB_ICONWARNING = 0x30
MB_ICONINFORMATION = 0x40
MB_SETFOREGROUND = 0x10000
MB_TOPMOST = 0x40000

ERROR_ALREADY_EXISTS = 183
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# --------------------------------------------------------------- structures
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, W.WPARAM, W.LPARAM)


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", W.HWND), ("message", W.UINT), ("wParam", W.WPARAM),
                ("lParam", W.LPARAM), ("time", W.DWORD), ("pt", W.POINT),
                ("lPrivate", W.DWORD)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", W.UINT), ("style", W.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                ("hCursor", HCURSOR), ("hbrBackground", W.HBRUSH),
                ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR),
                ("hIconSm", W.HICON)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG),
                ("biPlanes", W.WORD), ("biBitCount", W.WORD),
                ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG),
                ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", W.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", W.BYTE), ("BlendFlags", W.BYTE),
                ("SourceConstantAlpha", W.BYTE), ("AlphaFormat", W.BYTE)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT),
                ("rcWork", W.RECT), ("dwFlags", W.DWORD)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", W.DWORD), ("scanCode", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", W.DWORD), ("u", _INPUTUNION)]


# ---------------------------------------------------------------- functions
def _fn(dll, name, restype, *argtypes):
    f = getattr(dll, name)
    f.restype = restype
    f.argtypes = argtypes
    return f


RegisterClassExW = _fn(user32, "RegisterClassExW", W.ATOM, ctypes.POINTER(WNDCLASSEXW))
CreateWindowExW = _fn(user32, "CreateWindowExW", W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR,
                      W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                      W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID)
DefWindowProcW = _fn(user32, "DefWindowProcW", LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
DestroyWindow = _fn(user32, "DestroyWindow", W.BOOL, W.HWND)
ShowWindow = _fn(user32, "ShowWindow", W.BOOL, W.HWND, ctypes.c_int)
IsWindowVisible = _fn(user32, "IsWindowVisible", W.BOOL, W.HWND)
FindWindowW = _fn(user32, "FindWindowW", W.HWND, W.LPCWSTR, W.LPCWSTR)
GetWindowTextW = _fn(user32, "GetWindowTextW", ctypes.c_int, W.HWND, W.LPWSTR, ctypes.c_int)
GetMessageW = _fn(user32, "GetMessageW", W.BOOL, ctypes.POINTER(MSG), W.HWND, W.UINT, W.UINT)
TranslateMessage = _fn(user32, "TranslateMessage", W.BOOL, ctypes.POINTER(MSG))
DispatchMessageW = _fn(user32, "DispatchMessageW", LRESULT, ctypes.POINTER(MSG))
PostMessageW = _fn(user32, "PostMessageW", W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
PostQuitMessage = _fn(user32, "PostQuitMessage", None, ctypes.c_int)
SetTimer = _fn(user32, "SetTimer", ULONG_PTR, W.HWND, ULONG_PTR, W.UINT, W.LPVOID)
KillTimer = _fn(user32, "KillTimer", W.BOOL, W.HWND, ULONG_PTR)
RegisterHotKey = _fn(user32, "RegisterHotKey", W.BOOL, W.HWND, ctypes.c_int, W.UINT, W.UINT)
UnregisterHotKey = _fn(user32, "UnregisterHotKey", W.BOOL, W.HWND, ctypes.c_int)
GetForegroundWindow = _fn(user32, "GetForegroundWindow", W.HWND)
GetWindowThreadProcessId = _fn(user32, "GetWindowThreadProcessId", W.DWORD, W.HWND,
                               ctypes.POINTER(W.DWORD))
MonitorFromWindow = _fn(user32, "MonitorFromWindow", W.HMONITOR, W.HWND, W.DWORD)
MonitorFromPoint = _fn(user32, "MonitorFromPoint", W.HMONITOR, W.POINT, W.DWORD)
GetMonitorInfoW = _fn(user32, "GetMonitorInfoW", W.BOOL, W.HMONITOR, ctypes.POINTER(MONITORINFO))
GetCursorPos = _fn(user32, "GetCursorPos", W.BOOL, ctypes.POINTER(W.POINT))
UpdateLayeredWindow = _fn(user32, "UpdateLayeredWindow", W.BOOL, W.HWND, W.HDC,
                          ctypes.POINTER(W.POINT), ctypes.POINTER(W.SIZE), W.HDC,
                          ctypes.POINTER(W.POINT), W.COLORREF,
                          ctypes.POINTER(BLENDFUNCTION), W.DWORD)
SetWindowPos = _fn(user32, "SetWindowPos", W.BOOL, W.HWND, W.HWND, ctypes.c_int,
                   ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT)
GetDC = _fn(user32, "GetDC", W.HDC, W.HWND)
ReleaseDC = _fn(user32, "ReleaseDC", ctypes.c_int, W.HWND, W.HDC)
SendInput = _fn(user32, "SendInput", W.UINT, W.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
GetAsyncKeyState = _fn(user32, "GetAsyncKeyState", W.SHORT, ctypes.c_int)
SetWindowsHookExW = _fn(user32, "SetWindowsHookExW", W.HHOOK, ctypes.c_int, HOOKPROC,
                        W.HINSTANCE, W.DWORD)
UnhookWindowsHookEx = _fn(user32, "UnhookWindowsHookEx", W.BOOL, W.HHOOK)
CallNextHookEx = _fn(user32, "CallNextHookEx", LRESULT, W.HHOOK, ctypes.c_int, W.WPARAM, W.LPARAM)
MessageBoxW = _fn(user32, "MessageBoxW", ctypes.c_int, W.HWND, W.LPCWSTR, W.LPCWSTR, W.UINT)
OpenClipboard = _fn(user32, "OpenClipboard", W.BOOL, W.HWND)
CloseClipboard = _fn(user32, "CloseClipboard", W.BOOL)
EmptyClipboard = _fn(user32, "EmptyClipboard", W.BOOL)
GetClipboardData = _fn(user32, "GetClipboardData", W.HANDLE, W.UINT)
SetClipboardData = _fn(user32, "SetClipboardData", W.HANDLE, W.UINT, W.HANDLE)
IsClipboardFormatAvailable = _fn(user32, "IsClipboardFormatAvailable", W.BOOL, W.UINT)
EnumClipboardFormats = _fn(user32, "EnumClipboardFormats", W.UINT, W.UINT)
RegisterClipboardFormatW = _fn(user32, "RegisterClipboardFormatW", W.UINT, W.LPCWSTR)
GetClipboardOwner = _fn(user32, "GetClipboardOwner", W.HWND)
GetClipboardSequenceNumber = _fn(user32, "GetClipboardSequenceNumber", W.DWORD)

GlobalAlloc = _fn(kernel32, "GlobalAlloc", W.HGLOBAL, W.UINT, ctypes.c_size_t)
GlobalLock = _fn(kernel32, "GlobalLock", W.LPVOID, W.HGLOBAL)
GlobalUnlock = _fn(kernel32, "GlobalUnlock", W.BOOL, W.HGLOBAL)
GlobalFree = _fn(kernel32, "GlobalFree", W.HGLOBAL, W.HGLOBAL)
GlobalSize = _fn(kernel32, "GlobalSize", ctypes.c_size_t, W.HGLOBAL)
GetModuleHandleW = _fn(kernel32, "GetModuleHandleW", W.HMODULE, W.LPCWSTR)
CreateMutexW = _fn(kernel32, "CreateMutexW", W.HANDLE, W.LPVOID, W.BOOL, W.LPCWSTR)
CloseHandle = _fn(kernel32, "CloseHandle", W.BOOL, W.HANDLE)
OpenProcess = _fn(kernel32, "OpenProcess", W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
QueryFullProcessImageNameW = _fn(kernel32, "QueryFullProcessImageNameW", W.BOOL, W.HANDLE,
                                 W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD))

CreateCompatibleDC = _fn(gdi32, "CreateCompatibleDC", W.HDC, W.HDC)
DeleteDC = _fn(gdi32, "DeleteDC", W.BOOL, W.HDC)
CreateDIBSection = _fn(gdi32, "CreateDIBSection", W.HBITMAP, W.HDC, ctypes.POINTER(BITMAPINFO),
                       W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD)
SelectObject = _fn(gdi32, "SelectObject", W.HGDIOBJ, W.HDC, W.HGDIOBJ)
DeleteObject = _fn(gdi32, "DeleteObject", W.BOOL, W.HGDIOBJ)


# ------------------------------------------------------------------ helpers
def set_dpi_awareness() -> None:
    """Per-monitor DPI awareness, чтобы плашка была чёткой и в нужном месте."""
    try:
        f = user32.SetProcessDpiAwarenessContext
        f.restype = W.BOOL
        f.argtypes = [W.HANDLE]
        if f(W.HANDLE(-4)):  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            return
    except AttributeError:
        pass
    try:
        if shcore is not None:
            shcore.SetProcessDpiAwareness(2)
            return
    except OSError:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def monitor_for_foreground() -> tuple[W.RECT, float]:
    """Рабочая область и масштаб монитора, на котором активное окно."""
    hwnd = GetForegroundWindow()
    if hwnd:
        hmon = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    else:
        pt = W.POINT()
        GetCursorPos(ctypes.byref(pt))
        hmon = MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    GetMonitorInfoW(hmon, ctypes.byref(mi))
    scale = 1.0
    if shcore is not None:
        dx, dy = W.UINT(), W.UINT()
        try:
            if shcore.GetDpiForMonitor(W.HMONITOR(hmon), MDT_EFFECTIVE_DPI,
                                       ctypes.byref(dx), ctypes.byref(dy)) == 0 and dx.value:
                scale = dx.value / 96.0
        except OSError:
            pass
    return mi.rcWork, scale


def foreground_process_name() -> str:
    """Имя exe активного окна (в нижнем регистре), '' если не удалось."""
    hwnd = GetForegroundWindow()
    if not hwnd:
        return ""
    pid = W.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = W.DWORD(len(buf))
        if QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1].lower()
        return ""
    finally:
        CloseHandle(h)


def window_text(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(1024)
    GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def message_box(text: str, title: str, flags: int = MB_OK | MB_ICONINFORMATION) -> int:
    return MessageBoxW(None, text, title, flags | MB_SETFOREGROUND | MB_TOPMOST)


def modifiers_down() -> bool:
    for vk in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN):
        if GetAsyncKeyState(vk) & 0x8000:
            return True
    return False


def key_down(vk: int) -> bool:
    return bool(GetAsyncKeyState(vk) & 0x8000)
