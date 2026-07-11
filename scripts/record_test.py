import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import time

import sounddevice as sd

from app.audio.recorder import Recorder

if __name__ == "__main__":
    rec = Recorder(device=None)
    print("錄音 3 秒，請說話...")
    rec.start(); time.sleep(3)
    audio = rec.stop()
    print(f"樣本數 {len(audio)}，峰值 {abs(audio).max():.3f}，回放中...")
    sd.play(audio, 16000); sd.wait()
