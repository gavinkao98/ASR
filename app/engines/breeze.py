"""Breeze-ASR-25（CT2 int8_float16）。聯發科模型：原生台灣繁中＋中英夾雜。"""
import numpy as np

from app.engines.base import Engine
from app.logger import get_logger
from app.paths import BREEZE_DIR

log = get_logger("breeze")


class BreezeEngine(Engine):
    name = "breeze"
    has_punct = False          # Task 21 實測後若有標點改 True 並同步 config 預設
    outputs_simplified = False

    def __init__(self, force_language: str | None = None):
        self._model = None
        self._lang = force_language

    def load(self) -> None:
        from faster_whisper import WhisperModel
        log.info("loading Breeze-ASR-25 ...")
        self._model = WhisperModel(
            str(BREEZE_DIR), device="cuda", compute_type="int8_float16"
        )
        log.info("Breeze loaded")

    def unload(self) -> None:
        self._model = None
        import gc
        gc.collect()

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        assert self._model is not None, "engine not loaded"
        segments, _info = self._model.transcribe(
            samples,
            language=self._lang,               # None=自動偵測（純英文句也能辨）
            beam_size=5,
            temperature=0.0,                    # 防幻覺
            condition_on_previous_text=False,   # 防幻覺傳染
            vad_filter=False,                   # 前面已用 silero-vad 裁切
        )
        return "".join(seg.text for seg in segments).strip()
