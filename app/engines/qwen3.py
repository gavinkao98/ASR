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
from app.logger import get_logger, log_dir
from app.paths import LLAMA_SERVER_DIR, QWEN3_DIR
from app.postprocess.repeat_guard import looks_repetitive

log = get_logger("qwen3")


# 不帶 -c/-np 時，這版 llama-server 預設開 65536×4 slots 的 KV cache（26 萬 tokens 級），
# 12GB VRAM 塞不下、驅動默默溢到系統記憶體 → 平常正常、VRAM 一緊就換頁地獄（GPU 滿載
# 很久＋全機卡）甚至 CUDA 配置失敗直接死。實測音訊 ~13 tokens/秒，錄音上限 120 秒
# ≈ 1,600 tokens，4096 含輸出仍有兩倍餘裕。
_CTX_SIZE = 4096


def _build_cmd(exe, model, mmproj, port: int, *, use_gpu: bool) -> list[str]:
    cmd = [str(exe), "-m", str(model), "--mmproj", str(mmproj),
           "--host", "127.0.0.1", "--port", str(port),
           "-c", str(_CTX_SIZE), "-np", "1"]
    cmd += ["-ngl", "99"] if use_gpu else ["-ngl", "0"]
    return cmd


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


def _bind_to_job(proc: subprocess.Popen):
    """把子行程綁進 kill-on-close 的 Job Object：本程式死亡（含被強殺）時 OS 自動收掉
    llama-server，不留孤兒佔 VRAM。回傳 job handle，呼叫端必須保存引用（GC 關閉即觸發）。"""
    import win32api
    import win32con
    import win32job

    job = win32job.CreateJobObject(None, "")
    info = win32job.QueryInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation)
    info["BasicLimitInformation"]["LimitFlags"] |= (
        win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
    win32job.SetInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation, info)
    handle = win32api.OpenProcess(
        win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, proc.pid)
    try:
        win32job.AssignProcessToJobObject(job, handle)
    finally:
        handle.Close()
    return job


def _open_server_log(path, max_bytes: int = 10_000_000):
    """開啟 llama-server 落地 log（附加模式）；過大就先輪替成 .1，只留上一份。"""
    if path.exists() and path.stat().st_size > max_bytes:
        bak = path.with_suffix(".log.1")
        bak.unlink(missing_ok=True)
        path.rename(bak)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("ab")


def _max_tokens(audio_seconds: float) -> int:
    """輸出 token 上限：64 起步＋12/秒（中文語速 ~5 字/秒的兩倍餘裕），封頂 2048。
    擋住模型跳針時的無限生成——沒有上限的話會一路吐到 context 塞滿。"""
    return int(min(2048, 64 + audio_seconds * 12))


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
        self._job = None  # Job Object handle；只要活著，llama-server 就跟主程式同生共死

    def load(self) -> None:
        exe = next(LLAMA_SERVER_DIR.rglob("llama-server.exe"))
        ggufs = sorted(QWEN3_DIR.glob("*.gguf"))
        model = next(p for p in ggufs if not p.name.lower().startswith("mmproj"))
        mmproj = next(p for p in ggufs if p.name.lower().startswith("mmproj"))
        self._port = _free_port()
        cmd = _build_cmd(exe, model, mmproj, self._port, use_gpu=self._use_gpu)
        log.info("starting llama-server: %s", " ".join(cmd))
        logf = _open_server_log(log_dir() / "llama-server.log")
        try:
            self._proc = subprocess.Popen(
                cmd, cwd=str(exe.parent),
                stdout=logf, stderr=subprocess.STDOUT,  # 落檔：死掉才查得到原因
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        finally:
            logf.close()  # 子行程已繼承 handle，自己這份可關
        try:
            self._job = _bind_to_job(self._proc)
        except Exception:  # noqa: BLE001 - 綁定失敗不影響功能，只是少了保險
            log.warning("job object 綁定失敗，主程式異常退出時可能留下孤兒 llama-server")
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
        if self._job is not None:
            self._job.Close()  # kill-on-close：萬一上面沒收乾淨，這裡必殺
            self._job = None

    def _ask(self, samples: np.ndarray, rate: int, temperature: float = 0.0) -> str:
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
            "temperature": temperature,
            "max_tokens": _max_tokens(len(samples) / rate),
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
        if looks_repetitive(text):  # 模型跳針：temp=0 重跑必然同結果，改用 0.3 才有機會跳出
            log.warning("repetitive output, retrying with temperature: %r", text[:80])
            text = self._ask(samples, sample_rate, temperature=0.3)
            if looks_repetitive(text):  # 仍跳針：回空白（寧可沒輸出，不貼垃圾、不再燒 GPU）
                log.warning("still repetitive after retry, dropping: %r", text[:80])
                return ""
        return text
