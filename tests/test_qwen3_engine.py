import numpy as np
import pytest

from app import downloads

pytestmark = pytest.mark.skipif(not downloads.qwen3_ready(), reason="需先下載 Qwen3（選配）")


def test_qwen3_lifecycle_and_silence():
    from app.engines.qwen3 import Qwen3Engine
    eng = Qwen3Engine()
    eng.load()
    try:
        out = eng.transcribe(np.zeros(16000, dtype=np.float32))
        assert isinstance(out, str)
    finally:
        eng.unload()
