"""Qwen3-ASR-1.7B via llama-server 子行程。原生標點；輸出簡體（chain 會轉繁）。"""
import base64
import io
import socket
import subprocess
import time
import wave

import numpy as np
import requests

from app.engines.base import Engine
from app.logger import get_logger
from app.paths import LLAMA_SERVER_DIR, QWEN3_DIR
from app.postprocess.repeat_guard import looks_repetitive

log = get_logger("qwen3")


def _free_port() -> int:
    """向 OS 要一個當下空閒的埠，避免與其他程式相撞（如 NVIDIA Broadcast 佔用 18100）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _extract_asr_text(content: str) -> str:
    """Qwen3-ASR GGUF 會把輸出包成 'language <LANG><asr_text><內容>'，取 <asr_text> 之後的純文字。
    無語音時 <LANG> 為 None、內容為空；未來版本若加上 </asr_text> 結尾標記也一併去除。"""
    if "<asr_text>" in content:
        content = content.split("<asr_text>", 1)[1]
    return content.split("</asr_text>", 1)[0].strip()


def _to_wav_b64(samples: np.ndarray, rate: int) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return base64.b64encode(buf.getvalue()).decode()


class Qwen3Engine(Engine):
    name = "qwen3"
    has_punct = True
    outputs_simplified = True

    def __init__(self, use_gpu: bool = True):
        self._proc: subprocess.Popen | None = None
        self._use_gpu = use_gpu
        self._port: int | None = None

    def load(self) -> None:
        exe = next(LLAMA_SERVER_DIR.rglob("llama-server.exe"))
        ggufs = sorted(QWEN3_DIR.glob("*.gguf"))
        model = next(p for p in ggufs if not p.name.lower().startswith("mmproj"))
        mmproj = next(p for p in ggufs if p.name.lower().startswith("mmproj"))
        self._port = _free_port()
        cmd = [str(exe), "-m", str(model), "--mmproj", str(mmproj),
               "--host", "127.0.0.1", "--port", str(self._port)]
        cmd += ["-ngl", "99"] if self._use_gpu else ["-ngl", "0"]
        log.info("starting llama-server: %s", " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd, cwd=str(exe.parent),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for _ in range(120):  # 最多等 60 秒
            try:
                if requests.get(f"http://127.0.0.1:{self._port}/health", timeout=1).ok:
                    log.info("llama-server ready")
                    return
            except requests.RequestException:
                pass
            if self._proc.poll() is not None:
                raise RuntimeError("llama-server 啟動即退出，請手動執行上列 cmd 看錯誤")
            time.sleep(0.5)
        self.unload()  # 逾時未就緒：收掉子行程，避免殘留佔顯卡拖累下次載入
        raise TimeoutError("llama-server 60 秒內未就緒")

    def unload(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    def _ask(self, samples: np.ndarray, rate: int) -> str:
        payload = {
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "input_audio",
                     "input_audio": {"data": _to_wav_b64(samples, rate),
                                     "format": "wav"}},
                    {"type": "text", "text": "請轉錄這段音訊。"},
                ],
            }],
            "temperature": 0.0,
        }
        r = requests.post(f"http://127.0.0.1:{self._port}/v1/chat/completions",
                          json=payload, timeout=120)
        r.raise_for_status()
        return _extract_asr_text(r.json()["choices"][0]["message"]["content"])

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> str:
        if self._proc is None or self._proc.poll() is not None:
            log.warning("llama-server 不在了，自動重啟")  # 子行程當掉自動恢復
            self.unload()
            self.load()
        text = self._ask(samples, sample_rate)
        if looks_repetitive(text):  # 已知 bug：偵測到重複就重試一次
            log.warning("repetitive output, retrying once: %r", text[:80])
            text = self._ask(samples, sample_rate)
        return text
