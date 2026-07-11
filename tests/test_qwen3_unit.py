"""Qwen3 引擎單元測試（不啟動 llama-server；整合測試見 test_qwen3_engine.py）。"""
from app.engines.qwen3 import _build_cmd


def _pair_in(cmd: list[str], flag: str, value: str) -> bool:
    return any(cmd[i] == flag and cmd[i + 1] == value for i in range(len(cmd) - 1))


def test_build_cmd_caps_context_and_slots():
    """KV cache 必須壓在 -c 4096、單一 slot：不帶參數時 llama-server 預設值
    （65536×4 slots）會撐爆 12GB VRAM、溢到系統記憶體（GPU 卡死 bug 主因）。"""
    cmd = _build_cmd("srv.exe", "m.gguf", "mm.gguf", 1234, use_gpu=True)
    assert _pair_in(cmd, "-c", "4096")
    assert _pair_in(cmd, "-np", "1")
    assert _pair_in(cmd, "--port", "1234")
    assert _pair_in(cmd, "-ngl", "99")


def test_build_cmd_cpu_mode():
    cmd = _build_cmd("srv.exe", "m.gguf", "mm.gguf", 1234, use_gpu=False)
    assert _pair_in(cmd, "-ngl", "0")


def test_max_tokens_scales_with_audio_length():
    """輸出上限隨音檔長度走：中文語速 ~5 字/秒，12 tokens/秒已是兩倍餘裕。
    模型跳針時不再無限生成（先前無上限，會一路吐到 context 塞滿、GPU 白燒幾十秒）。"""
    from app.engines.qwen3 import _max_tokens
    assert _max_tokens(2.0) == 64 + 24          # 短句
    assert _max_tokens(120.0) == 64 + 1440      # 錄音上限 120 秒
    assert _max_tokens(10_000.0) == 2048        # 絕對上限


REPETITIVE = "你好你好你好你好你好你好你好你好"


def _engine_with_fake_ask(replies):
    """替換網路邊界 _ask，錄下每次呼叫的 temperature；其餘 transcribe 邏輯走真實碼。"""
    import numpy as np
    from app.engines.qwen3 import Qwen3Engine

    eng = Qwen3Engine()
    eng._proc = type("P", (), {"poll": staticmethod(lambda: None)})()  # 假裝 server 活著
    calls = []

    def fake_ask(samples, rate, temperature=0.0):
        calls.append(temperature)
        return replies[len(calls) - 1]

    eng._ask = fake_ask
    return eng, calls, np.zeros(16000, dtype=np.float32)


def test_transcribe_retries_repetitive_with_temperature():
    eng, calls, audio = _engine_with_fake_ask([REPETITIVE, "正常句子。"])
    assert eng.transcribe(audio) == "正常句子。"
    assert calls == [0.0, 0.3]  # 重試必須換 temperature：0.0 重跑只會得到同樣的跳針


def test_transcribe_drops_text_still_repetitive_after_retry():
    eng, calls, audio = _engine_with_fake_ask([REPETITIVE, REPETITIVE])
    assert eng.transcribe(audio) == ""  # 寧可空白也不把跳針垃圾貼給使用者
    assert len(calls) == 2  # 不做第三次：GPU 時間寶貴


def test_transcribe_normal_output_single_call():
    eng, calls, audio = _engine_with_fake_ask(["正常句子。"])
    assert eng.transcribe(audio) == "正常句子。"
    assert calls == [0.0]


def test_open_server_log_appends(tmp_path):
    """llama-server 的 stdout/stderr 要落檔（先前丟 DEVNULL，死掉完全看不到原因）。"""
    from app.engines.qwen3 import _open_server_log
    p = tmp_path / "llama-server.log"
    p.write_bytes(b"old\n")
    with _open_server_log(p) as f:
        f.write(b"new\n")
    assert p.read_bytes() == b"old\nnew\n"


def test_open_server_log_rotates_oversized(tmp_path):
    from app.engines.qwen3 import _open_server_log
    p = tmp_path / "llama-server.log"
    p.write_bytes(b"x" * 100)
    with _open_server_log(p, max_bytes=50) as f:
        f.write(b"fresh\n")
    assert p.read_bytes() == b"fresh\n"
    assert (tmp_path / "llama-server.log.1").read_bytes() == b"x" * 100


def test_job_object_kills_child_when_handle_closes():
    """主程式死亡（含被強殺）時 OS 要自動收掉 llama-server：先前 Python 異常退出
    會留下孤兒行程佔著 VRAM（Windows 錯誤報告已有一筆 RADAR 記憶體暴漲事件）。"""
    import subprocess
    import sys

    from app.engines.qwen3 import _bind_to_job

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        job = _bind_to_job(child)
        assert job is not None
        job.Close()  # 模擬主程式死亡：最後一個 job handle 關閉
        child.wait(timeout=5)  # 沒被收掉會 TimeoutExpired
    finally:
        if child.poll() is None:
            child.kill()
