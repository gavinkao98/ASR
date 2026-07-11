"""讓 pytest 也能載入 cuDNN/cuBLAS：在收集測試前先觸發 main.py 的 NVIDIA DLL 注入。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import main  # noqa: E402,F401  # import 時即執行 _inject_nvidia_dlls()
