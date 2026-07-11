import numpy as np
import pytest

from app import downloads
from app.audio.vad import trim_speech

pytestmark = pytest.mark.skipif(not downloads.vad_ready(), reason="需先下載 VAD 模型")


def test_silence_returns_none():
    silence = np.zeros(16000 * 2, dtype=np.float32)
    assert trim_speech(silence) is None


def test_returns_float32_when_speech_like():
    # 不保證雜訊觸發 VAD，只驗 API 形狀：回 None 或 float32 一維陣列
    noise = (np.random.default_rng(0).standard_normal(16000) * 0.1).astype(np.float32)
    out = trim_speech(noise)
    assert out is None or (out.dtype == np.float32 and out.ndim == 1)
