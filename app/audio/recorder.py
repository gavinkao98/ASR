"""16kHz 單聲道錄音。start/stop 由 pipeline 呼叫；level 給浮窗顯示音量。"""
import numpy as np
import sounddevice as sd

from app.logger import get_logger

log = get_logger("recorder")
SAMPLE_RATE = 16000
MAX_SECONDS = 120  # 安全上限，防按著不放


class Recorder:
    def __init__(self, device: str | None):
        self._device = device
        self._stream: sd.InputStream | None = None
        self._buffers: list[np.ndarray] = []
        self.level = 0.0

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            log.warning("audio status: %s", status)
        if sum(len(b) for b in self._buffers) < SAMPLE_RATE * MAX_SECONDS:
            self._buffers.append(indata[:, 0].copy())
        self.level = float(np.abs(indata).max())

    def start(self) -> None:
        self._buffers = []
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                device=self._device, callback=self._on_audio,
            )
            self._stream.start()
        except Exception:  # noqa: BLE001 - 指定裝置不可用（拔掉/被占用）→ 退回系統預設
            log.warning("裝置 %s 開啟失敗，退回系統預設麥克風", self._device)
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                device=None, callback=self._on_audio,
            )
            self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.level = 0.0
        return self._collect()

    def _collect(self) -> np.ndarray:
        if not self._buffers:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._buffers)

    @staticmethod
    def list_devices() -> list[str]:
        return sorted({d["name"] for d in sd.query_devices()
                       if d["max_input_channels"] > 0})
