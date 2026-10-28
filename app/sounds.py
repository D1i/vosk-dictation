"""Короткие звуки включения/выключения (по умолчанию выключены в config.json)."""
from __future__ import annotations

import logging
import os

import config

log = logging.getLogger("sounds")


def play(name: str, enabled: bool) -> None:
    if not enabled:
        return
    path = os.path.join(config.APP_DIR, "assets", f"{name}.wav")
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
    except Exception:  # noqa: BLE001
        log.debug("sound failed", exc_info=True)
