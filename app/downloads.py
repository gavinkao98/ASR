"""模型下載。進度以 callback(progress: float 0~1, label: str) 回報，供精靈/模型頁共用。"""
import fnmatch
import tarfile
import zipfile
from pathlib import Path
from typing import Callable, Optional

import requests

from app import paths
from app.logger import get_logger

log = get_logger("downloads")
ProgressCb = Callable[[float, str], None]

PUNCT_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
             "punctuation-models/"
             "sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12.tar.bz2")
VAD_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
           "asr-models/silero_vad.onnx")
BREEZE_REPOS = ["SoybeanMilk/faster-whisper-Breeze-ASR-25",
                "phate334/Breeze-ASR-25-ct2"]
QWEN3_GGUF_REPO = "ggml-org/Qwen3-ASR-1.7B-GGUF"  # 官方 llama.cpp 專用 GGUF（Q8_0）
LLAMACPP_REPO = "ggml-org/llama.cpp"


def pick_asset(names: list[str], patterns: list[str]) -> Optional[str]:
    for pat in patterns:
        for name in names:
            if fnmatch.fnmatch(name.lower(), pat.lower()):
                return name
    return None


def _stream_download(url: str, dest: Path, cb: ProgressCb, label: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    cb(done / total, label)
    log.info("downloaded %s -> %s", url, dest)


def download_breeze(cb: ProgressCb) -> None:
    from huggingface_hub import snapshot_download
    last_err = None
    for repo in BREEZE_REPOS:
        try:
            cb(0.0, f"下載 Breeze-ASR-25（{repo}）")
            snapshot_download(repo_id=repo, local_dir=paths.BREEZE_DIR)
            cb(1.0, "Breeze-ASR-25 完成")
            return
        except Exception as e:  # noqa: BLE001 - 換備援 repo
            last_err = e
            log.warning("breeze repo %s failed: %s", repo, e)
    raise RuntimeError(f"Breeze 下載失敗：{last_err}")


def download_punct(cb: ProgressCb) -> None:
    tmp = paths.MODELS_DIR / "punct.tar.bz2"
    _stream_download(PUNCT_URL, tmp, cb, "下載標點模型")
    with tarfile.open(tmp, "r:bz2") as tar:
        tar.extractall(paths.MODELS_DIR)
    extracted = paths.MODELS_DIR / "sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12"
    if paths.PUNCT_DIR.exists():
        import shutil
        shutil.rmtree(paths.PUNCT_DIR)
    extracted.rename(paths.PUNCT_DIR)
    tmp.unlink()


def download_vad(cb: ProgressCb) -> None:
    _stream_download(VAD_URL, paths.VAD_MODEL, cb, "下載 VAD 模型")


def _github_release_assets(repo: str) -> list[dict]:
    r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", timeout=30)
    r.raise_for_status()
    return r.json()["assets"]


def _download_and_extract(url: str, cb: ProgressCb, label: str) -> None:
    tmp = paths.MODELS_DIR / "llama_dl.zip"
    _stream_download(url, tmp, cb, label)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(paths.LLAMA_SERVER_DIR)  # 各 zip 檔都攤在根目錄，合併到同一層
    tmp.unlink()


def download_qwen3(cb: ProgressCb, use_gpu: bool = True) -> None:
    # 1) 模型：官方 ggml GGUF（Q8_0 主模型 + mmproj 音訊投影）；走 HF snapshot，已存在會略過。
    from huggingface_hub import snapshot_download
    cb(0.0, "下載 Qwen3-ASR GGUF 模型")
    snapshot_download(repo_id=QWEN3_GGUF_REPO, local_dir=paths.QWEN3_DIR,
                      allow_patterns=["*Q8_0*"])

    # 2) llama-server（Windows）：GPU→CUDA 12.4，否則→Vulkan（免 CUDA、通吃各家顯卡）。
    assets = _github_release_assets(LLAMACPP_REPO)
    names = [a["name"] for a in assets]
    by_name = {a["name"]: a["browser_download_url"] for a in assets}
    if use_gpu:
        server = pick_asset(names, ["llama-*-bin-win-cuda-12.4-x64.zip", "*win-cuda*x64*.zip"])
    else:
        server = pick_asset(names, ["llama-*-bin-win-vulkan-x64.zip", "*win-cpu*x64*.zip"])
    if not server:
        raise RuntimeError(f"找不到 llama-server Windows 包，實際資產：{names}")
    _download_and_extract(by_name[server], cb, "下載 llama-server")

    # 3) CUDA runtime（cudart/cublas）：CUDA 版 llama-server 需要，解到與 exe 同目錄才載得到。
    if use_gpu:
        cudart = pick_asset(names, ["cudart-llama-bin-win-cuda-12.4-x64.zip", "cudart-*cuda*x64.zip"])
        if not cudart:
            raise RuntimeError(f"找不到 cudart 包，實際資產：{names}")
        _download_and_extract(by_name[cudart], cb, "下載 CUDA runtime")
    cb(1.0, "Qwen3-ASR 就緒")


def breeze_ready() -> bool:
    return (paths.BREEZE_DIR / "model.bin").exists()


def punct_ready() -> bool:
    return paths.PUNCT_DIR.exists() and any(paths.PUNCT_DIR.glob("*.onnx"))


def vad_ready() -> bool:
    return paths.VAD_MODEL.exists()


def qwen3_ready() -> bool:
    has_model = paths.QWEN3_DIR.exists() and any(paths.QWEN3_DIR.glob("*.gguf"))
    has_server = any(paths.LLAMA_SERVER_DIR.rglob("llama-server.exe"))
    return has_model and has_server
