"""Генерирует app/assets: icon.ico, start.wav, stop.wav. Запуск: python tools/make_assets.py"""
import math
import os
import struct
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

from painter import Painter  # noqa: E402

ASSETS = os.path.join(ROOT, "app", "assets")
os.makedirs(ASSETS, exist_ok=True)

# --- иконка
p = Painter()
big = p.app_icon("icon", 256, fill=0.955)
big.save(os.path.join(ASSETS, "icon.ico"),
         sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
big.save(os.path.join(ASSETS, "icon.png"))


# --- звуки
def tone(path, freqs, dur=0.07, vol=0.18, rate=44100):
    frames = bytearray()
    for f in freqs:
        n = int(dur * rate)
        for i in range(n):
            env = min(1.0, i / (0.006 * rate), (n - i) / (0.03 * rate))
            v = vol * env * math.sin(2 * math.pi * f * i / rate)
            frames += struct.pack("<h", int(v * 32767))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


tone(os.path.join(ASSETS, "start.wav"), [740, 988])
tone(os.path.join(ASSETS, "stop.wav"), [988, 659])
print("assets written:", sorted(os.listdir(ASSETS)))
