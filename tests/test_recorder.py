"""Тесты логики записи разговора без звука и Windows: диаризация, лог,
кадры RPC и полный обмен RPC с фальшивым «Discord». Запуск: python tests/test_recorder.py"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from diarize import LogWriter, SpeakerTimeline  # noqa: E402
import rpc  # noqa: E402


def test_timeline():
    tl = SpeakerTimeline()
    tl.set_names({"1": "Аня", "2": "Боря"})
    tl.start("1", 10.0); tl.stop("1", 13.0)      # Аня 10..13
    tl.start("2", 12.5); tl.stop("2", 16.0)      # Боря 12.5..16
    # фраза 10.2..12.4 — целиком Аня
    uid, nick = tl.speaker_for(10.2, 12.4)
    assert nick == "Аня", (uid, nick)
    # фраза 14..15.5 — целиком Боря
    assert tl.speaker_for(14.0, 15.5)[1] == "Боря"
    # фраза 12.6..13.0 пересекается с обоими, но Боря дольше? Аня до 13 (0.4), Боря с 12.5 (0.4) -> граница
    ov = tl.overlaps(11.0, 16.0)
    assert ov["1"] > 0 and ov["2"] > 0
    # исключение себя
    assert tl.speaker_for(10.2, 12.4, exclude={"1"})[1] is None
    # открытый интервал (ещё говорит)
    tl.start("2", 20.0)
    assert tl.speaker_for(20.5, 21.0)[1] == "Боря"
    print("timeline OK")


def test_logwriter():
    path = tempfile.mktemp(suffix=".txt")
    w = LogWriter(path, merge_gap_sec=5.0)
    w.open("# шапка\n\n")
    w.write("Аня", "привет", "10:00:00", 100.0)
    w.write("Аня", "как дела", "10:00:03", 103.0)     # склеится (тот же ник, <5с)
    w.write("Боря", "нормально", "10:00:06", 106.0)   # новый ник -> новая строка
    w.write("Аня", "ну и хорошо", "10:00:20", 120.0)  # разрыв >5с -> новая строка
    w.close("# конец\n")
    text = open(path, encoding="utf-8").read()
    assert "[10:00:00] Аня: привет как дела" in text, text
    assert "[10:00:06] Боря: нормально" in text, text
    assert "[10:00:20] Аня: ну и хорошо" in text, text
    os.remove(path)
    print("logwriter OK")


def test_frames():
    for op, payload in [(0, {"v": 1, "client_id": "x"}), (1, {"cmd": "PING"})]:
        data = rpc.pack(op, payload)
        buf = bytearray(data)
        def recv(n, buf=buf):
            out = bytes(buf[:n]); del buf[:n]; return out
        got_op, got = rpc.read_frame(recv)
        assert got_op == op and got == payload, (got_op, got)
    print("frames OK")


class FakeDiscord:
    """Фальшивый Discord поверх транспорта RPC: отвечает на команды по nonce."""

    def __init__(self, channel):
        self.channel = channel
        self._buf = bytearray()
        self._cv = threading.Condition()
        self._closed = False
        self.authorized = False
        self.authenticated = False
        self.subscribed = set()

    # транспорт, как ждёт RpcClient
    def connect(self):
        return True

    def _push(self, op, payload):
        with self._cv:
            self._buf += rpc.pack(op, payload)
            self._cv.notify_all()

    def send(self, data):
        op, length = rpc.struct.unpack("<II", data[:8])
        payload = rpc.json.loads(data[8:8 + length]) if length else {}
        if op == rpc.OP_HANDSHAKE:
            self._push(rpc.OP_FRAME, {"cmd": "DISPATCH", "evt": "READY",
                                      "data": {"v": 1, "user": {"id": "0"}}})
            return
        cmd = payload.get("cmd"); nonce = payload.get("nonce")
        args = payload.get("args") or {}
        data_out = {}
        if cmd == "AUTHORIZE":
            self.authorized = True
            data_out = {"code": "THECODE"}
        elif cmd == "AUTHENTICATE":
            self.authenticated = True
            data_out = {"user": {"id": "0"}, "scopes": args.get("scopes", [])}
        elif cmd == "SUBSCRIBE":
            self.subscribed.add(payload.get("evt"))
        elif cmd == "UNSUBSCRIBE":
            self.subscribed.discard(payload.get("evt"))
        elif cmd == "GET_SELECTED_VOICE_CHANNEL":
            data_out = self.channel
        self._push(rpc.OP_FRAME, {"cmd": cmd, "nonce": nonce, "data": data_out})

    def emit(self, evt, data):
        self._push(rpc.OP_FRAME, {"cmd": "DISPATCH", "evt": evt, "data": data})

    def recv(self, n):
        with self._cv:
            while len(self._buf) < n and not self._closed:
                self._cv.wait(timeout=2.0)
                if len(self._buf) < n and not self._closed:
                    raise ConnectionError("timeout")
            out = bytes(self._buf[:n]); del self._buf[:n]
            return out

    def close(self):
        with self._cv:
            self._closed = True
            self._cv.notify_all()


class MemTokenStore:
    def __init__(self, token=None):
        self.token = token
    def load(self): return self.token
    def save(self, tok): self.token = tok
    def clear(self): self.token = None


class Collector:
    def __init__(self):
        self.channel = None
        self.names = {}
        self.speaking = []
        self.states = []
        self.done = threading.Event()
    def on_voice_channel(self, cid, names, merge=False, channel_name=None):
        self.channel = cid
        if merge:
            self.names.update(names)
        else:
            self.names = dict(names)
        if names:
            self.done.set()
    def on_speaking(self, uid, sp, t):
        self.speaking.append((uid, sp))
    def on_state(self, text):
        self.states.append(text)


def run_rpc(token, expect_authorize):
    channel = {"id": "555", "name": "General", "voice_states": [
        {"nick": "Аня", "user": {"id": "1", "username": "anya"}},
        {"nick": "Боря", "user": {"id": "2", "username": "borya"}},
    ]}
    fake = FakeDiscord(channel)
    posted = {}
    def http_post(url, fields):
        posted.update(fields)
        return {"access_token": "AT", "refresh_token": "RT", "expires_in": 604800}
    store = MemTokenStore(token)
    cb = Collector()
    client = rpc.RpcClient("appid", "secret", store, cb,
                           make_transport=lambda: fake, http_post=http_post)
    client.start()
    assert cb.done.wait(5), "канал не пришёл; состояния: %s" % cb.states
    assert cb.channel == "555" and cb.names == {"1": "Аня", "2": "Боря"}, (cb.channel, cb.names)
    assert fake.authenticated
    assert fake.authorized == expect_authorize, (fake.authorized, expect_authorize)
    assert "SPEAKING_START" in fake.subscribed
    if expect_authorize:
        assert posted.get("code") == "THECODE" and store.token["access_token"] == "AT"
    # событие речи
    fake.emit("SPEAKING_START", {"user_id": "1", "channel_id": "555"})
    fake.emit("SPEAKING_STOP", {"user_id": "1", "channel_id": "555"})
    # обновление ника
    fake.emit("VOICE_STATE_UPDATE", {"nick": "Анна", "user": {"id": "1"}})
    time.sleep(0.3)
    assert ("1", True) in cb.speaking and ("1", False) in cb.speaking, cb.speaking
    assert cb.names.get("1") == "Анна", cb.names
    client.stop()
    time.sleep(0.2)
    print("rpc flow OK (authorize=%s)" % expect_authorize)


def test_rpc_with_token():
    run_rpc({"access_token": "OLD", "refresh_token": "RT"}, expect_authorize=False)


def test_rpc_authorize():
    run_rpc(None, expect_authorize=True)


def main():
    test_timeline()
    test_track_pipeline()
    test_logwriter()
    test_frames()
    test_rpc_with_token()
    test_rpc_authorize()
    print("ALL OK")


def test_track_pipeline():
    """_Track: захват -> (фейковый) Vosk -> строка лога с привязкой к говорящему."""
    import types, json as _json, tempfile as _tf, time as _t
    import diarize, recorder as rec_mod

    # фейковый vosk: выдаёт одну фразу с временами слов
    fake = types.ModuleType("vosk")
    class FakeRec:
        def __init__(self, model, rate): self.done = False
        def SetWords(self, on): pass
        def AcceptWaveform(self, data):
            if not self.done:
                self.done = True
                return True
            return False
        def Result(self):
            return _json.dumps({"text": "привет всем",
                                "result": [{"word": "привет", "start": 0.1, "end": 0.5},
                                           {"word": "всем", "start": 0.5, "end": 0.9}]})
        def FinalResult(self): return _json.dumps({"text": ""})
    fake.KaldiRecognizer = FakeRec
    sys.modules["vosk"] = fake

    class FakeSource:
        rate = 16000
        def __init__(self): self.n = 0
        def open(self): pass
        def read(self):
            self.n += 1
            if self.n > 3:
                return None
            return b"\x00\x10" * 1600
        def close(self): pass

    tl = diarize.SpeakerTimeline()
    tl.set_name("1", "Аня")
    tl.start("1", _t.monotonic() - 0.05)   # открытый интервал -> перекроет любую фразу
    path = _tf.mktemp(suffix=".txt")
    w = diarize.LogWriter(path); w.open()
    def attr(a, b):
        uid, nick = tl.speaker_for(a, b)
        return nick or "Собеседник"
    tr = rec_mod._Track("loopback", FakeSource(), object(), tl, w, attr, True)
    tr.start(); tr.join(timeout=5)
    w.close()
    text = open(path, encoding="utf-8").read()
    assert "Аня: привет всем" in text, text
    os.remove(path)
    print("track pipeline OK")


if __name__ == "__main__":
    main()
    os._exit(0)
