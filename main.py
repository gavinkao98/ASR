"""進入點。務必在 import ctranslate2/faster_whisper 之前先注入 NVIDIA DLL 路徑。"""
import os
import sys
from pathlib import Path


def _inject_nvidia_dlls() -> None:
    """把 pip 安裝的 cuBLAS/cuDNN DLL 目錄加進 DLL 搜尋路徑（Windows 專用）。"""
    try:
        import nvidia  # noqa: F401
    except ImportError:
        return
    nvidia_root = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for bin_dir in nvidia_root.glob("*/bin"):
        os.add_dll_directory(str(bin_dir))


_inject_nvidia_dlls()

if __name__ == "__main__":
    from app.paths import ensure_dirs
    ensure_dirs()
    print("skeleton OK")
