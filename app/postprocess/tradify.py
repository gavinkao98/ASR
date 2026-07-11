from opencc import OpenCC

_cc = OpenCC("s2twp")  # 簡體 → 台灣正體＋台灣用語


def to_taiwan(text: str) -> str:
    return _cc.convert(text)
