from abc import ABC, abstractmethod

import numpy as np


class Engine(ABC):
    """辨識引擎統一介面。實作者需執行緒安全（pipeline 由單一 worker 執行緒呼叫）。"""

    name: str
    has_punct: bool            # 自帶標點？
    outputs_simplified: bool   # 輸出簡體？

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def unload(self) -> None: ...

    @abstractmethod
    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        """samples: float32 一維。回傳原始辨識文字（後處理交給 chain）。"""
