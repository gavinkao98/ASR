import numpy as np

from app.audio.recorder import Recorder


def test_buffer_accumulates_via_callback():
    rec = Recorder(device=None)
    rec._buffers.clear()
    frames = np.ones((1600, 1), dtype=np.float32)
    rec._on_audio(frames, 1600, None, None)
    rec._on_audio(frames * 0.5, 1600, None, None)
    out = rec._collect()
    assert out.shape == (3200,) and out.dtype == np.float32
    assert abs(out[:1600].mean() - 1.0) < 1e-6


def test_level_meter_updates():
    rec = Recorder(device=None)
    rec._on_audio(np.full((1600, 1), 0.5, dtype=np.float32), 1600, None, None)
    assert 0.4 < rec.level <= 1.0
