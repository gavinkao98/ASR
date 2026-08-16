"""CLI：下載預設引擎所需模型（Qwen3 + VAD）。--breeze 額外下載 Breeze 與標點模型。"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import main  # noqa: F401  # DLL 注入
from app import downloads, gpu
from app.paths import ensure_dirs


def cb(p, label):
    print(f"\r{label}: {p*100:5.1f}%", end="", flush=True)


if __name__ == "__main__":
    # 這支 CLI 繞過設定精靈，所以硬體檢查要自己做一次——否則在沒有 NVIDIA 顯示卡的
    # 機器上會下載 3.6GB 之後才在啟動 llama-server 時失敗。--force 留給「先在別台機器
    # 下載、之後再搬過去」這種情境。
    env = gpu.detect()
    if not env["available"] and "--force" not in sys.argv:
        print(f"中止：需要 NVIDIA 顯示卡與驅動程式（{env['detail']}）。")
        print("辨識在 GPU 上執行，此機器沒有可用的 CUDA 裝置。")
        print("若確定要下載（例如之後搬到別台機器用），加上 --force。")
        sys.exit(1)

    ensure_dirs()
    downloads.download_vad(cb); print()
    downloads.download_qwen3(cb); print()
    if "--breeze" in sys.argv:
        downloads.download_punct(cb); print()
        downloads.download_breeze(cb); print()
    print("完成：", downloads.qwen3_ready(), downloads.vad_ready())
