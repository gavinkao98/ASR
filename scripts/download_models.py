"""CLI：下載預設引擎所需模型（Breeze + 標點 + VAD）。--qwen3 加下載 Qwen3。"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import main  # noqa: F401  # DLL 注入
from app import downloads
from app.paths import ensure_dirs


def cb(p, label):
    print(f"\r{label}: {p*100:5.1f}%", end="", flush=True)


if __name__ == "__main__":
    ensure_dirs()
    downloads.download_vad(cb); print()
    downloads.download_punct(cb); print()
    downloads.download_breeze(cb); print()
    if "--qwen3" in sys.argv:
        downloads.download_qwen3(cb); print()
    print("完成：", downloads.breeze_ready(), downloads.punct_ready(), downloads.vad_ready())
