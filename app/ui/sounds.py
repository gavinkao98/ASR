"""提示音：start(升調)/done(降調)/empty(短低音)/error(雙低音)。非阻塞播放。"""
import wave
from pathlib import Path

import numpy as np
import winsound

from app.paths import ASSETS_DIR

_SPECS = {  # name: (freq_from, freq_to, ms)
    "start": (523, 784, 120),
    "done": (784, 523, 120),
    "empty": (330, 330, 150),
    "error": (262, 196, 220),
}


def _ensure(name: str) -> Path:
    p = ASSETS_DIR / f"{name}.wav"
    if not p.exists():
        f0, f1, ms = _SPECS[name]
        rate, n = 44100, int(44100 * ms / 1000)
        t = np.linspace(0, ms / 1000, n, endpoint=False)
        freq = np.linspace(f0, f1, n)
        tone = (np.sin(2 * np.pi * freq * t) * np.hanning(n) * 0.4 * 32767)
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(tone.astype(np.int16).tobytes())
    return p


def play(name: str, enabled: bool = True) -> None:
    if not enabled:
        return
    winsound.PlaySound(str(_ensure(name)),
                       winsound.SND_FILENAME | winsound.SND_ASYNC)
