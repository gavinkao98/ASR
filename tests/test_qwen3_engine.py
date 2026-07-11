import numpy as np
import pytest
import requests

from app import downloads

pytestmark = pytest.mark.skipif(not downloads.qwen3_ready(), reason="需先下載 Qwen3（選配）")


def test_qwen3_lifecycle_and_silence():
    from app.engines.qwen3 import Qwen3Engine
    from app.logger import log_dir
    eng = Qwen3Engine()
    eng.load()
    try:
        # KV cache 必須被壓住：預設 65536×4 slots 會撐爆 12GB VRAM（GPU 卡死 bug 主因）
        props = requests.get(f"http://127.0.0.1:{eng._port}/props", timeout=5).json()
        assert props["total_slots"] == 1
        assert props["default_generation_settings"]["n_ctx"] == 4096
        # server 輸出要落檔，死掉才查得到原因
        assert (log_dir() / "llama-server.log").stat().st_size > 0
        out = eng.transcribe(np.zeros(16000, dtype=np.float32))
        assert isinstance(out, str)
    finally:
        eng.unload()
