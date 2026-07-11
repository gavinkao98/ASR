"""CLI：下載預設引擎所需模型（Qwen3 + VAD）。--breeze 額外下載 Breeze 與標點模型。"""
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
    downloads.download_qwen3(cb); print()
    if "--breeze" in sys.argv:
        downloads.download_punct(cb); print()
        downloads.download_breeze(cb); print()
    print("完成：", downloads.qwen3_ready(), downloads.vad_ready())
