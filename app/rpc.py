"""Клиент Discord RPC поверх локального именованного канала (discord-ipc-N).

Узнаёт, в каком голосовом канале ты сейчас, кто там (ники) и кто говорит.
Аудио не трогает — только «кто и когда говорит». Работает с ТВОИМ приложением
Discord (его создаёшь один раз на discord.com/developers): для владельца и
тестеров приложения доступ к RPC разрешён без модерации.

Кадр IPC: 8-байтовый заголовок (opcode, длина — два uint32 little-endian) + JSON.
Транспорт и http-обмен вынесены, чтобы логику можно было протестировать с моками.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import struct
import threading
import time

log = logging.getLogger("rpc")

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

SCOPES = ["rpc", "rpc.voice.read"]
TOKEN_URL = "https://discord.com/api/oauth2/token"
REDIRECT_URI = "http://localhost"


# ------------------------------------------------------------------ framing
def pack(op: int, payload: dict) -> bytes:
    data = json.dumps(payload).encode("utf-8")
    return struct.pack("<II", op, len(data)) + data


def read_frame(recv) -> tuple[int, dict]:
    """recv(n) -> ровно n байт (или ошибка). Возвращает (opcode, payload)."""
    header = _recv_exact(recv, 8)
    op, length = struct.unpack("<II", header)
    data = _recv_exact(recv, length) if length else b""
    try:
        payload = json.loads(data.decode("utf-8")) if data else {}
    except ValueError:
        payload = {}
    return op, payload


def _recv_exact(recv, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = recv(n - len(buf))
        if not chunk:
            raise ConnectionError("канал закрыт")
        buf += chunk
    return bytes(buf)


# ---------------------------------------------------------------- transport
class PipeTransport:
    """Именованный канал Windows \\\\.\\pipe\\discord-ipc-N через kernel32."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes as W
        self._c = ctypes
        self._W = W
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.handle = None

    def connect(self) -> bool:
        import ctypes
        from ctypes import wintypes as W
        GENERIC_RW = 0x80000000 | 0x40000000
        OPEN_EXISTING = 3
        INVALID = ctypes.c_void_p(-1).value
        CreateFileW = self.k.CreateFileW
        CreateFileW.restype = W.HANDLE
        CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p,
                                W.DWORD, W.DWORD, W.HANDLE]
        for n in range(10):
            path = rf"\\.\pipe\discord-ipc-{n}"
            h = CreateFileW(path, GENERIC_RW, 0, None, OPEN_EXISTING, 0, None)
            if h != INVALID and h:
                self.handle = h
                log.info("connected to %s", path)
                return True
        return False

    def send(self, data: bytes) -> None:
        import ctypes
        from ctypes import wintypes as W
        WriteFile = self.k.WriteFile
        WriteFile.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD,
                              ctypes.POINTER(W.DWORD), ctypes.c_void_p]
        written = W.DWORD(0)
        if not WriteFile(self.handle, data, len(data), ctypes.byref(written), None):
            raise ConnectionError(f"WriteFile: {ctypes.get_last_error()}")

    def recv(self, n: int) -> bytes:
        import ctypes
        from ctypes import wintypes as W
        ReadFile = self.k.ReadFile
        ReadFile.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD,
                             ctypes.POINTER(W.DWORD), ctypes.c_void_p]
        buf = (ctypes.c_char * n)()
        got = W.DWORD(0)
        if not ReadFile(self.handle, buf, n, ctypes.byref(got), None):
            raise ConnectionError(f"ReadFile: {ctypes.get_last_error()}")
        return bytes(buf[:got.value])

    def wait_readable(self, timeout: float) -> bool:
        """Неблокирующе ждём данные в канале (PeekNamedPipe). True — есть; False — таймаут."""
        import ctypes, time
        from ctypes import wintypes as W
        Peek = self.k.PeekNamedPipe
        Peek.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD,
                         ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD),
                         ctypes.POINTER(W.DWORD)]
        avail = W.DWORD(0)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not Peek(self.handle, None, 0, None, ctypes.byref(avail), None):
                raise ConnectionError(f"PeekNamedPipe: {ctypes.get_last_error()}")
            if avail.value > 0:
                return True
            time.sleep(0.05)
        return False

    def close(self) -> None:
        if self.handle:
            try:
                self.k.CloseHandle(self.handle)
            except Exception:  # noqa: BLE001
                pass
            self.handle = None


def http_post_form(url: str, fields: dict) -> dict:
    """POST application/x-www-form-urlencoded -> JSON (stdlib, для обмена токена)."""
    import urllib.parse
    import urllib.request
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VoskDictation/1.0",
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


# ------------------------------------------------------------------- client
class RpcClient(threading.Thread):
    """Фоновый поток: держит соединение, зовёт колбэки при смене канала и речи.

    callbacks:
      on_voice_channel(channel_id: str | None, names: dict[str, str])
      on_speaking(user_id: str, speaking: bool, t: float)
      on_state(text: str)   — короткий статус для интерфейса/журнала
    """

    def __init__(self, client_id: str, client_secret: str, token_store,
                 callbacks, make_transport=PipeTransport, http_post=http_post_form):
        super().__init__(daemon=True, name="discord-rpc")
        self.client_id = str(client_id).strip()
        self.client_secret = str(client_secret).strip()
        self.token_store = token_store          # объект с load()/save(dict)/clear()
        self.cb = callbacks
        self.make_transport = make_transport
        self.http_post = http_post
        self.tr = None
        self._stopev = threading.Event()
        self._nonces = itertools.count(1)
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()  # сериализует чтение/запись на синхронном канале
        self._channel: str | None = None
        self.error: str | None = None
        self.authed = False

    # --- команды ----------------------------------------------------------
    def _send_cmd(self, cmd: str, args: dict | None = None, evt: str | None = None,
                  wait: float = 8.0) -> dict | None:
        nonce = str(next(self._nonces))
        payload = {"cmd": cmd, "nonce": nonce}
        if args is not None:
            payload["args"] = args
        if evt is not None:
            payload["evt"] = evt
        box = {"event": threading.Event(), "data": None, "error": None}
        with self._lock:
            self._pending[nonce] = box
        with self._io_lock:
            self.tr.send(pack(OP_FRAME, payload))
        deadline = time.monotonic() + wait
        while not box["event"].wait(0.3):
            if self._stopev.is_set():
                raise ConnectionError("остановлено")
            if time.monotonic() > deadline:
                with self._lock:
                    self._pending.pop(nonce, None)
                raise TimeoutError(f"нет ответа на {cmd}")
        if box["error"]:
            raise RuntimeError(f"{cmd}: {box['error']}")
        return box["data"]

    def _subscribe(self, evt: str, args: dict | None = None) -> None:
        try:
            self._send_cmd("SUBSCRIBE", args=args or {}, evt=evt, wait=6.0)
        except Exception as e:  # noqa: BLE001
            log.warning("subscribe %s failed: %s", evt, e)

    # --- жизненный цикл ---------------------------------------------------
    def stop(self) -> None:
        self._stopev.set()
        if self.tr is not None:
            self.tr.close()

    def run(self) -> None:
        try:
            self._connect_and_serve()
        except Exception as e:  # noqa: BLE001
            self.error = str(e) or e.__class__.__name__
            log.exception("rpc failed")
            self._state(f"Discord: {self.error}")
        finally:
            if self.tr is not None:
                self.tr.close()
            self.authed = False
            self.cb.on_voice_channel(None, {})

    def _state(self, text: str) -> None:
        try:
            self.cb.on_state(text)
        except Exception:  # noqa: BLE001
            pass

    def _connect_and_serve(self) -> None:
        if not self.client_id:
            raise RuntimeError("не задан client_id приложения Discord")
        self.tr = self.make_transport()
        if not self.tr.connect():
            raise RuntimeError("Discord не запущен (канал discord-ipc не найден)")
        self.tr.send(pack(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id}))
        if not self.tr.wait_readable(8.0):
            raise ConnectionError("Discord не ответил на рукопожатие (нет READY)")
        op, payload = read_frame(self.tr.recv)     # READY
        if op == OP_CLOSE:
            raise RuntimeError(payload.get("message", "handshake отклонён"))
        self._note_self((payload.get("data") or {}).get("user"))
        reader = threading.Thread(target=self._reader, daemon=True, name="rpc-reader")
        reader.start()
        self._authenticate()
        self._subscribe("VOICE_CHANNEL_SELECT")
        self._refresh_channel()
        self._state("Discord подключён")
        log.info("rpc ready, authed=%s", self.authed)
        while not self._stopev.is_set():
            time.sleep(0.5)

    # --- авторизация ------------------------------------------------------
    def _authenticate(self) -> None:
        token = self.token_store.load()
        access = token.get("access_token") if token else None
        if access and self._try_auth(access):
            return
        if token and token.get("refresh_token") and self.client_secret:
            new = self._refresh(token["refresh_token"])
            if new and self._try_auth(new["access_token"]):
                return
        # полная авторизация с согласием пользователя в Discord
        if not self.client_secret:
            raise RuntimeError("нужен client_secret приложения (см. настройку Discord)")
        self._state("Разрешите доступ в окне Discord…")
        data = self._send_cmd("AUTHORIZE",
                              args={"client_id": self.client_id, "scopes": SCOPES},
                              wait=120.0)
        code = (data or {}).get("code")
        if not code:
            raise RuntimeError("авторизация отклонена в Discord")
        log.info("authorize code received, exchanging for token…")
        token = self._exchange(code)
        log.info("token received, authenticating…")
        if not self._try_auth(token["access_token"]):
            raise RuntimeError("не удалось пройти AUTHENTICATE")

    def _note_self(self, user: dict | None) -> None:
        if not user or not user.get("id"):
            return
        fn = getattr(self.cb, "on_self", None)
        if fn:
            fn(str(user["id"]), user.get("global_name") or user.get("username"))

    def _try_auth(self, access_token: str) -> bool:
        try:
            data = self._send_cmd("AUTHENTICATE", args={"access_token": access_token})
            self._note_self((data or {}).get("user"))
            self.authed = True
            return True
        except Exception as e:  # noqa: BLE001
            log.info("authenticate failed: %s", e)
            return False

    def _exchange(self, code: str) -> dict:
        tok = self.http_post(TOKEN_URL, {
            "client_id": self.client_id, "client_secret": self.client_secret,
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": REDIRECT_URI})
        if "access_token" not in tok:
            raise RuntimeError(f"обмен кода не удался: {tok}")
        self.token_store.save(tok)
        return tok

    def _refresh(self, refresh_token: str) -> dict | None:
        try:
            tok = self.http_post(TOKEN_URL, {
                "client_id": self.client_id, "client_secret": self.client_secret,
                "grant_type": "refresh_token", "refresh_token": refresh_token})
            if "access_token" in tok:
                self.token_store.save(tok)
                return tok
        except Exception as e:  # noqa: BLE001
            log.info("token refresh failed: %s", e)
        return None

    # --- канал и участники ------------------------------------------------
    def _names_from_states(self, states) -> dict[str, str]:
        names = {}
        for st in states or []:
            user = st.get("user") or {}
            uid = str(user.get("id") or "")
            nick = st.get("nick") or user.get("global_name") or user.get("username")
            if uid and nick:
                names[uid] = nick
        return names

    def _refresh_channel(self) -> None:
        try:
            data = self._send_cmd("GET_SELECTED_VOICE_CHANNEL") or {}
        except Exception as e:  # noqa: BLE001
            log.info("get channel failed: %s", e)
            return
        self._set_channel(data)

    def _set_channel(self, data: dict | None) -> None:
        channel_id = str(data.get("id")) if data and data.get("id") else None
        if self._channel and self._channel != channel_id:
            for evt in ("SPEAKING_START", "SPEAKING_STOP", "VOICE_STATE_CREATE",
                        "VOICE_STATE_UPDATE", "VOICE_STATE_DELETE"):
                try:
                    self._send_cmd("UNSUBSCRIBE", args={"channel_id": self._channel},
                                   evt=evt, wait=4.0)
                except Exception:  # noqa: BLE001
                    pass
        self._channel = channel_id
        names = self._names_from_states(data.get("voice_states") if data else None)
        if channel_id:
            for evt in ("SPEAKING_START", "SPEAKING_STOP", "VOICE_STATE_CREATE",
                        "VOICE_STATE_UPDATE", "VOICE_STATE_DELETE"):
                self._subscribe(evt, {"channel_id": channel_id})
        self.cb.on_voice_channel(channel_id, names,
                                 channel_name=(data or {}).get("name"))

    # --- приём кадров -----------------------------------------------------
    def _reader(self) -> None:
        try:
            while not self._stopev.is_set():
                # неблокирующий опрос: держать блокирующий ReadFile нельзя — на синхронном
                # канале он не даёт отправлять команды (write висит за незавершённым read)
                if not self.tr.wait_readable(0.2):
                    continue
                with self._io_lock:
                    op, payload = read_frame(self.tr.recv)
                if op == OP_CLOSE:
                    self._state("Discord отключился")
                    break
                if op == OP_PING:
                    with self._io_lock:
                        self.tr.send(pack(OP_PONG, payload))
                    continue
                if op != OP_FRAME:
                    continue
                self._dispatch(payload)
        except Exception as e:  # noqa: BLE001
            if not self._stopev.is_set():
                log.info("reader stopped: %s", e)
        finally:
            self._stopev.set()

    def _dispatch(self, payload: dict) -> None:
        nonce = payload.get("nonce")
        if nonce:
            with self._lock:
                box = self._pending.pop(nonce, None)
            if box is not None:
                if payload.get("evt") == "ERROR":
                    box["error"] = (payload.get("data") or {}).get("message", "ERROR")
                else:
                    box["data"] = payload.get("data")
                box["event"].set()
            return
        evt = payload.get("evt")
        data = payload.get("data") or {}
        now = time.monotonic()
        if evt in ("SPEAKING_START", "SPEAKING_STOP"):
            uid = str(data.get("user_id") or "")
            if uid:
                self.cb.on_speaking(uid, evt == "SPEAKING_START", now)
        elif evt == "VOICE_CHANNEL_SELECT":
            cid = data.get("channel_id")
            if cid:
                try:
                    full = self._send_cmd("GET_SELECTED_VOICE_CHANNEL") or {}
                except Exception:  # noqa: BLE001
                    full = {"id": cid}
                self._set_channel(full)
            else:
                self._set_channel(None)
        elif evt in ("VOICE_STATE_CREATE", "VOICE_STATE_UPDATE"):
            names = self._names_from_states([data])
            if names:
                self.cb.on_voice_channel(self._channel, names, merge=True)


class TokenStore:
    """Хранит OAuth-токен Discord в отдельном файле (не в config.json — он секретный)."""

    def __init__(self, path: str):
        self.path = path

    def load(self) -> dict | None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def save(self, token: dict) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(token, f)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        except OSError as e:
            log.warning("cannot save token: %s", e)

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass
