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
QWEN3_REPO = "HaujetZhao/Qwen3-ASR-GGUF"
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


def download_qwen3(cb: ProgressCb, use_gpu: bool = True) -> None:
    assets = _github_release_assets(QWEN3_REPO)
    names = [a["name"] for a in assets]
    by_name = {a["name"]: a["browser_download_url"] for a in assets}

    model = pick_asset(names, ["*q8_0.gguf", "*q4*.gguf"])
    mmproj = pick_asset(names, ["mmproj*.gguf"])
    if not model or not mmproj:
        raise RuntimeError(f"在 {QWEN3_REPO} release 找不到 GGUF 資產，實際資產：{names}")
    _stream_download(by_name[model], paths.QWEN3_DIR / model, cb, "下載 Qwen3 模型")
    _stream_download(by_name[mmproj], paths.QWEN3_DIR / mmproj, cb, "下載 Qwen3 mmproj")

    server_pats = (["*win-cuda*x64*.zip", "*win-cuda*.zip"] if use_gpu
                   else ["*win-cpu*x64*.zip", "*win-vulkan*x64*.zip"])
    server = pick_asset(names, server_pats)
    server_url = by_name.get(server) if server else None
    if not server_url:  # 該 repo 沒附 → 到 llama.cpp 官方 release 拿
        assets = _github_release_assets(LLAMACPP_REPO)
        names = [a["name"] for a in assets]
        by_name = {a["name"]: a["browser_download_url"] for a in assets}
        server = pick_asset(names, server_pats)
        if not server:
            raise RuntimeError(f"找不到 llama-server Windows 包，實際資產：{names}")
        server_url = by_name[server]
    tmp = paths.MODELS_DIR / "llama-server.zip"
    _stream_download(server_url, tmp, cb, "下載 llama-server")
    with zipfile.ZipFile(tmp) as z:
        z.extractall(paths.LLAMA_SERVER_DIR)
    tmp.unlink()


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
