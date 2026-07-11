"""實測 Breeze 是否輸出標點：錄 3 句話，印原始輸出。"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import time

import main  # noqa: F401
from app.audio.recorder import Recorder
from app.audio.vad import trim_speech
from app.engines.breeze import BreezeEngine

if __name__ == "__main__":
    eng = BreezeEngine(); eng.load()
    rec = Recorder(device=None)
    for i in range(3):
        input(f"[{i+1}/3] 按 Enter 後錄 5 秒，請說一句含逗號語氣停頓的話...")
        rec.start(); time.sleep(5)
        audio = trim_speech(rec.stop())
        print("原始輸出：", repr(eng.transcribe(audio)) if audio is not None else "(無人聲)")
