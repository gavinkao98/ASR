"""silero-vad（sherpa-onnx 版）：找出語音段，裁掉頭尾靜音；整段無語音回 None。"""
from typing import Optional

import numpy as np
import sherpa_onnx

from app.paths import VAD_MODEL

SAMPLE_RATE = 16000
_PAD_SEC = 0.25  # 語音段前後各保留一點，避免裁掉氣音字頭字尾


def _new_vad() -> "sherpa_onnx.VoiceActivityDetector":
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = str(VAD_MODEL)
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_speech_duration = 0.15
    cfg.silero_vad.min_silence_duration = 0.25
    cfg.sample_rate = SAMPLE_RATE
    return sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=120)


def trim_speech(samples: np.ndarray) -> Optional[np.ndarray]:
    vad = _new_vad()
    window = 512  # silero v5+ 固定 512 樣本窗
    starts, ends = [], []
    for i in range(0, len(samples), window):
        vad.accept_waveform(samples[i:i + window])
    vad.flush()
    while not vad.empty():
        seg = vad.front
        starts.append(seg.start)
        ends.append(seg.start + len(seg.samples))
        vad.pop()
    if not starts:
        return None
    pad = int(_PAD_SEC * SAMPLE_RATE)
    lo = max(0, min(starts) - pad)
    hi = min(len(samples), max(ends) + pad)
    return samples[lo:hi].astype(np.float32)
