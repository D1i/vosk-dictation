# -*- coding: utf-8 -*-
"""ПОЛНАЯ авторизация Discord и сохранение токена в discord_token.json.
Показывает окно «Авторизовать» -> ждёт клика -> меняет код на токен (с User-Agent)
-> сохраняет токен -> AUTHENTICATE. Пишет журнал в build\\discord_probe.txt."""
import ctypes, json, os, struct, sys, time, urllib.parse, urllib.request, urllib.error
from ctypes import wintypes as W
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
import config
cfg, _ = config.load()
CID = str(cfg.get("discord_client_id", "")).strip()
CSECRET = str(cfg.get("discord_client_secret", "")).strip()
SCOPES = ["rpc", "rpc.voice.read"]
REDIRECT = "http://localhost"
TOKEN_PATH = os.path.join(ROOT, "discord_token.json")
out_path = os.path.join(ROOT, "build", "discord_probe.txt")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
OUT = open(out_path, "w", encoding="utf-8")
def p(*a):
    line=" ".join(str(x) for x in a); print(line); OUT.write(line+"\n"); OUT.flush()

def post_form(url, fields):
    body=urllib.parse.urlencode(fields).encode()
    req=urllib.request.Request(url, data=body, headers={
        "Content-Type":"application/x-www-form-urlencoded",
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) VoskDictation/1.0",
        "Accept":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"_raw": e.read().decode(errors="replace")}

k=ctypes.WinDLL("kernel32", use_last_error=True)
GRW=0x80000000|0x40000000; INVALID=ctypes.c_void_p(-1).value
CF=k.CreateFileW; CF.restype=W.HANDLE
CF.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,ctypes.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
handle=None
for n in range(10):
    h=CF(rf"\\.\pipe\discord-ipc-{n}",GRW,0,None,3,0,None)
    if h!=INVALID and h: handle=h; p("ipc discord-ipc-%d"%n); break
if not handle: p("Discord не запущен"); OUT.close(); sys.exit(1)
def send(op,pl):
    d=json.dumps(pl).encode(); b=struct.pack("<II",op,len(d))+d; w=W.DWORD(0)
    k.WriteFile(handle,b,len(b),ctypes.byref(w),None)
def recv(nb):
    b=(ctypes.c_char*nb)(); g=W.DWORD(0)
    if not k.ReadFile(handle,b,nb,ctypes.byref(g),None): raise OSError("ReadFile %d"%ctypes.get_last_error())
    return bytes(b[:g.value])
def rf():
    hd=b""
    while len(hd)<8: hd+=recv(8-len(hd))
    op,ln=struct.unpack("<II",hd); dt=b""
    while len(dt)<ln: dt+=recv(ln-len(dt))
    return op, json.loads(dt.decode()) if dt else {}
send(0,{"v":1,"client_id":CID})
op,pl=rf(); u=(pl.get("data") or {}).get("user") or {}
p("handshake user:", u.get("global_name"), u.get("id"))
p("\n>>> Отправляю AUTHORIZE. В Discord появится окно — нажми «Авторизовать».")
send(1,{"cmd":"AUTHORIZE","nonce":"a1","args":{"client_id":CID,"scopes":SCOPES}})
code=None
while True:
    try: op,pl=rf()
    except OSError as e: p("канал закрылся:",e); break
    if pl.get("nonce")=="a1":
        if pl.get("evt")=="ERROR":
            p("AUTHORIZE ошибка:", (pl.get('data') or {}).get('message')); break
        code=(pl.get("data") or {}).get("code"); p("Получен код авторизации."); break
if not code: p("!! кода нет — стоп."); OUT.close(); sys.exit(1)
p("Меняю код на токен (POST /oauth2/token, с User-Agent)…")
st,tok=post_form("https://discord.com/api/oauth2/token",
    {"client_id":CID,"client_secret":CSECRET,"grant_type":"authorization_code",
     "code":code,"redirect_uri":REDIRECT})
p("  HTTP",st,"| ключи:",list(tok.keys()))
if "access_token" not in tok:
    p("  !! обмен не удался:", json.dumps(tok,ensure_ascii=False)[:300]); OUT.close(); sys.exit(1)
with open(TOKEN_PATH,"w",encoding="utf-8") as f: json.dump(tok,f)
p("  ТОКЕН СОХРАНЁН ->", TOKEN_PATH, "| scope:", tok.get("scope"))
send(1,{"cmd":"AUTHENTICATE","nonce":"b1","args":{"access_token":tok["access_token"]}})
while True:
    try: op,pl=rf()
    except OSError as e: p("канал закрылся:",e); break
    if pl.get("nonce")=="b1":
        ok=pl.get("evt")!="ERROR"
        p("AUTHENTICATE:", "ОК ✓" if ok else json.dumps(pl,ensure_ascii=False)[:200])
        p("\n>>> ГОТОВО: авторизация прошла, токен сохранён." if ok else ">>> ошибка AUTHENTICATE"); break
OUT.close()
