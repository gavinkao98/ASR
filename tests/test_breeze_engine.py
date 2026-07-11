import numpy as np
import pytest

from app import downloads

pytestmark = pytest.mark.skipif(not downloads.breeze_ready(), reason="需先下載 Breeze")


def test_breeze_flags_and_silence():
    from app.engines.breeze import BreezeEngine
    eng = BreezeEngine()
    assert eng.outputs_simplified is False
    eng.load()
    try:
        out = eng.transcribe(np.zeros(16000, dtype=np.float32))
        assert isinstance(out, str)  # 靜音給空字串或幻覺短字皆可，不 crash 即過
    finally:
        eng.unload()
