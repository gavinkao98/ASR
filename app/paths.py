from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
WEB_DIR = ROOT / "web"
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
LOGS_DIR = DATA_DIR / "logs"
CONFIG_FILE = DATA_DIR / "config.json"
HOTWORDS_FILE = DATA_DIR / "hotwords.txt"
HISTORY_DB = DATA_DIR / "history.db"

BREEZE_DIR = MODELS_DIR / "breeze-asr-25-ct2"
PUNCT_DIR = MODELS_DIR / "punct-ct-transformer"
VAD_MODEL = MODELS_DIR / "silero_vad.onnx"
QWEN3_DIR = MODELS_DIR / "qwen3-asr-1.7b"
LLAMA_SERVER_DIR = MODELS_DIR / "llama-server"

def ensure_dirs() -> None:
    for d in (MODELS_DIR, DATA_DIR, ASSETS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
