"""logger 依 ASR_LOG_DIR 環境變數決定輸出目錄（pytest 用它把測試 log 與正式 log 隔離）。"""
from app.logger import get_logger


def test_logger_respects_env_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ASR_LOG_DIR", str(tmp_path))
    log = get_logger("env-dir-probe")  # 名稱唯一，避免撞到既有 handler 快取
    log.info("hello-env")
    for h in log.handlers:
        h.flush()
    assert "hello-env" in (tmp_path / "asr.log").read_text(encoding="utf-8")
