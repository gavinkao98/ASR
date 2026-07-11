"""讓 pytest 也能載入 cuDNN/cuBLAS：在收集測試前先觸發 main.py 的 NVIDIA DLL 注入。
同時把 log 導向暫存目錄，測試不再把 FakeEngine 之類的訊息寫進 data/logs/asr.log。"""
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("ASR_LOG_DIR", tempfile.mkdtemp(prefix="asr-test-logs-"))

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import main  # noqa: E402,F401  # import 時即執行 _inject_nvidia_dlls()
