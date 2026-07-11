import logging
from logging.handlers import RotatingFileHandler

from app.paths import LOGS_DIR


def get_logger(name: str = "asr") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOGS_DIR / "asr.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler())
    return logger
