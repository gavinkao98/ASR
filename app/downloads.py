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

# llama.cpp 幾乎每天發版，且 multimodal/音訊介面有過破壞性變更（詳見 Qwen3Engine._ask 的
# payload 格式）。抓 releases/latest 等於讓每個新使用者拿到「當天剛發布、從未與這份程式碼
# 一起測過」的 llama-server。釘死在實測可用的版本，升級改為有意識的決定。
#
# 升級步驟：改這個常數 → 刪掉 models/llama-server → 重跑下載 →
#           `pytest tests/test_qwen3_engine.py` 通過 → 端到端錄一句確認 → 才提交。
LLAMACPP_TAG = "b9964"  # 2026-07-11 發布；本專案實測基準版
_CUDA_VER = "12.4"      # llama-server build 與 cudart 必須用同一版，見 download_qwen3


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


def _github_release_assets(repo: str, tag: str) -> list[dict]:
    """取指定 tag 的 release 資產。刻意不提供「抓最新版」的選項——見 LLAMACPP_TAG。"""
    r = requests.get(f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
                     timeout=30)
    if r.status_code == 404:
        raise RuntimeError(
            f"{repo} 找不到 release {tag}；上游可能已刪除該版本，"
            f"需更新 downloads.LLAMACPP_TAG 並重新驗證相容性")
    r.raise_for_status()
    return r.json()["assets"]


def _download_and_extract(url: str, cb: ProgressCb, label: str) -> None:
    tmp = paths.MODELS_DIR / "llama_dl.zip"
    _stream_download(url, tmp, cb, label)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(paths.LLAMA_SERVER_DIR)  # 各 zip 檔都攤在根目錄，合併到同一層
    tmp.unlink()


def select_llama_assets(names: list[str]) -> list[tuple[str, str]]:
    """從 release 資產清單挑出 llama-server 與 cudart，回傳 [(資產名, 進度標籤)]。

    兩者的 CUDA 版本「必須一致」，所以由同一個 _CUDA_VER 導出檔名。上游同一個 release
    會同時提供 12.4 與 13.3；若各自用寬鬆 glob 挑選，可能拿到 server 13.3 + cudart 12.4
    的錯配組合——那會在執行期才炸，且錯誤訊息完全指不到真正原因。
    """
    picked = []
    for pattern, label in (
        (f"llama-*-bin-win-cuda-{_CUDA_VER}-x64.zip", "下載 llama-server"),
        (f"cudart-llama-bin-win-cuda-{_CUDA_VER}-x64.zip", "下載 CUDA runtime"),
    ):
        asset = pick_asset(names, [pattern])
        if not asset:
            raise RuntimeError(
                f"llama.cpp {LLAMACPP_TAG} 找不到符合 {pattern} 的資產。"
                f"上游可能改了命名或移除該 CUDA 版本，需更新 LLAMACPP_TAG/_CUDA_VER "
                f"並重新驗證。實際資產：{names}")
        picked.append((asset, label))
    return picked


def download_qwen3(cb: ProgressCb) -> None:
    """下載 Qwen3-ASR 所需的模型與 llama-server（CUDA build）。

    只有 CUDA 路徑。曾有一段 Vulkan/CPU 分支，但沒有任何呼叫端傳過 use_gpu=False，
    等於從未執行過、也無從驗證 Vulkan build 是否支援 Qwen3-ASR 的 input_audio 介面。
    留著死碼會讓 README 誤以為支援非 NVIDIA 硬體，故移除；若日後有環境可驗證，
    從 git 歷史取回即可。硬體需求由 Bridge.env_check() 在下載前擋。
    """
    # 1) 模型：官方 ggml GGUF（Q8_0 主模型 + mmproj 音訊投影）；走 HF snapshot，已存在會略過。
    from huggingface_hub import snapshot_download
    cb(0.0, "下載 Qwen3-ASR GGUF 模型")
    snapshot_download(repo_id=QWEN3_GGUF_REPO, local_dir=paths.QWEN3_DIR,
                      allow_patterns=["*Q8_0*"])

    # 2) llama-server（Windows CUDA build）＋ 3) 對應的 CUDA runtime。
    assets = _github_release_assets(LLAMACPP_REPO, LLAMACPP_TAG)
    by_name = {a["name"]: a["browser_download_url"] for a in assets}
    for name, label in select_llama_assets(list(by_name)):
        _download_and_extract(by_name[name], cb, label)
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
