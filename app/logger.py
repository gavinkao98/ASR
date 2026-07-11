import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.paths import LOGS_DIR


def log_dir() -> Path:
    """ASR_LOG_DIR 可整批改寫 log 輸出位置（pytest 靠它隔離，不汙染正式 log）。"""
    return Path(os.environ.get("ASR_LOG_DIR") or LOGS_DIR)


def get_logger(name: str = "asr") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        d / "asr.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler())
    return logger
