"""sherpa-onnx ct-punc 中英標點恢復。惰性載入單例（CPU、毫秒級）。"""
import threading

import sherpa_onnx

from app.paths import PUNCT_DIR

_lock = threading.Lock()
_punct = None


def _get():
    global _punct
    with _lock:
        if _punct is None:
            model = next(PUNCT_DIR.glob("model*.onnx"))
            cfg = sherpa_onnx.OfflinePunctuationConfig(
                model=sherpa_onnx.OfflinePunctuationModelConfig(
                    ct_transformer=str(model), num_threads=2
                )
            )
            _punct = sherpa_onnx.OfflinePunctuation(cfg)
    return _punct


def add_punct(text: str) -> str:
    if not text.strip():
        return text
    return _get().add_punctuation(text)
