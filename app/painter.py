"""Рисует плашку с микрофоном (Pillow). Не зависит от Windows."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Размеры в логических пикселях (умножаются на масштаб монитора)
PILL_W = 460
PILL_H = 60
PAD = 18            # место под тень
BADGE = 56          # область значка микрофона
TEXT_X = 68

BG = (26, 26, 30, 242)
BORDER = (255, 255, 255, 34)
TEXT = (242, 242, 245, 255)
TEXT_DIM = (160, 160, 170, 255)
HINT = (125, 125, 135, 255)
STATE_COLORS = {
    "listening": (229, 72, 77),
    "loading": (112, 112, 124),
    "error": (232, 150, 30),
    "icon": (229, 72, 77),
}

_FONT_FILES = {
    "regular": ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"],
    "semibold": ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
}


class Painter:
    def __init__(self):
        self._fonts: dict = {}
        self._bg: dict = {}
        self._badges: dict = {}
        self._base_key = None
        self._base_img = None

    # ------------------------------------------------------------------
    @staticmethod
    def size(scale: float) -> tuple[int, int]:
        return (round((PILL_W + 2 * PAD) * scale), round((PILL_H + 2 * PAD) * scale))

    def font(self, px: int, weight: str = "regular"):
        key = (px, weight)
        f = self._fonts.get(key)
        if f is None:
            for name in _FONT_FILES[weight]:
                try:
                    f = ImageFont.truetype(name, px)
                    break
                except OSError:
                    continue
            if f is None:
                f = ImageFont.load_default(px)
            self._fonts[key] = f
        return f

    # ------------------------------------------------------------------
    def background(self, s: float) -> Image.Image:
        img = self._bg.get(s)
        if img is not None:
            return img
        iw, ih = self.size(s)
        x0, y0 = round(PAD * s), round(PAD * s)
        x1, y1 = iw - x0, ih - y0
        r = (y1 - y0) / 2
        # мягкая тень
        mask = Image.new("L", (iw, ih), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [x0 + 2 * s, y0 + 4 * s, x1 - 2 * s, y1 + 3 * s], radius=r, fill=120)
        mask = mask.filter(ImageFilter.GaussianBlur(8 * s))
        shadow = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
        shadow.putalpha(mask)
        # сама плашка — с 3x сглаживанием
        k = 3
        big = Image.new("RGBA", (iw * k, ih * k), (0, 0, 0, 0))
        ImageDraw.Draw(big).rounded_rectangle(
            [x0 * k, y0 * k, x1 * k - 1, y1 * k - 1], radius=r * k,
            fill=BG, outline=BORDER, width=max(1, round(s * k)))
        pill = big.resize((iw, ih), Image.LANCZOS)
        img = Image.alpha_composite(shadow, pill)
        self._bg[s] = img
        return img

    def badge(self, s: float, state: str, level: float) -> Image.Image:
        step = max(0, min(20, round(level * 20)))
        key = (s, state, step)
        img = self._badges.get(key)
        if img is not None:
            return img
        k = 4
        size = round(BADGE * s)
        u = s * k
        c = size * k / 2
        big = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        color = STATE_COLORS.get(state, STATE_COLORS["loading"])
        r = 17 * u
        lv = step / 20
        if state == "listening":
            hr = r + (2.5 + 8.5 * lv) * u
            d.ellipse([c - hr, c - hr, c + hr, c + hr], fill=color + (int(45 + 70 * lv),))
        d.ellipse([c - r, c - r, c + r, c + r], fill=color + (255,))
        white = (255, 255, 255, 255)
        if state == "error":
            lw = 2.6 * u
            d.rounded_rectangle([c - lw / 2, c - 9 * u, c + lw / 2, c + 3 * u], radius=lw / 2, fill=white)
            d.ellipse([c - 1.7 * u, c + 5.5 * u, c + 1.7 * u, c + 8.9 * u], fill=white)
        else:
            lw = max(1, round(1.9 * u))
            d.rounded_rectangle([c - 3.8 * u, c - 10 * u, c + 3.8 * u, c + 2.6 * u],
                                radius=3.8 * u, fill=white)
            d.arc([c - 7 * u, c - 7.4 * u, c + 7 * u, c + 6.6 * u], start=0, end=180,
                  fill=white, width=lw)
            d.line([c, c + 6.6 * u, c, c + 10 * u], fill=white, width=lw)
            d.line([c - 4.2 * u, c + 10 * u, c + 4.2 * u, c + 10 * u], fill=white, width=lw)
        img = big.resize((size, size), Image.LANCZOS)
        self._badges[key] = img
        return img

    def app_icon(self, state: str, size: int, fill: float = 0.96) -> Image.Image:
        """Значок (круг с микрофоном) почти во весь кадр — для трея и .ico."""
        img = self.badge(size * fill / 34, state, 0.0)   # круг — 34 логических px
        x = (img.width - size) // 2
        return img.crop((x, x, x + size, x + size))

    # ------------------------------------------------------------------
    @staticmethod
    def fit(text: str, font, max_w: float, keep_end: bool = True) -> str:
        """Обрезает текст по ширине: keep_end=True — оставляет хвост (для диктовки),
        иначе — начало (для сообщений)."""
        if font.getlength(text) <= max_w:
            return text
        lo, hi = 0, len(text)
        if keep_end:
            while lo < hi:  # минимальный отрезанный префикс, чтобы хвост влез
                mid = (lo + hi) // 2
                if font.getlength("…" + text[mid:]) <= max_w:
                    hi = mid
                else:
                    lo = mid + 1
            return "…" + text[lo:]
        while lo < hi:  # максимальное начало, которое влезает
            mid = (lo + hi + 1) // 2
            if font.getlength(text[:mid].rstrip() + "…") <= max_w:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo].rstrip() + "…"

    def _base(self, s: float, main: str, dim: bool, hint: str, keep_end: bool) -> Image.Image:
        key = (s, main, dim, hint, keep_end)
        if self._base_key == key:
            return self._base_img
        img = self.background(s).copy()
        iw, _ = img.size
        pad = round(PAD * s)
        d = ImageDraw.Draw(img)
        tx = pad + round(TEXT_X * s)
        max_w = iw - pad - round(22 * s) - tx
        f_main = self.font(max(8, round(15.5 * s)), "regular")
        f_hint = self.font(max(7, round(11.5 * s)), "regular")
        main = " ".join(main.replace("\n", " ¶ ").split())
        d.text((tx, pad + round(23 * s)), self.fit(main, f_main, max_w, keep_end),
               font=f_main, fill=TEXT_DIM if dim else TEXT, anchor="lm")
        if hint:
            d.text((tx, pad + round(42.5 * s)), self.fit(hint, f_hint, max_w, False),
                   font=f_hint, fill=HINT, anchor="lm")
        self._base_key, self._base_img = key, img
        return img

    def render(self, s: float, state: str, main: str, dim: bool, hint: str,
               level: float) -> Image.Image:
        img = self._base(s, main, dim, hint, keep_end=(state == "listening")).copy()
        pad = round(PAD * s)
        b = self.badge(s, state, level)
        img.alpha_composite(b, (pad + round(6 * s), pad + round((PILL_H * s - b.height) / 2)))
        return img


def pulse(t: float) -> float:
    """Лёгкое «дыхание» значка, когда тихо."""
    return 0.06 + 0.05 * (1 + math.sin(t * 3.2)) / 2
