import re

# 2~20 字的片段連續重複 4 次以上 → 視為模型重複 bug
_LOOP = re.compile(r"(.{2,20})\1{3,}", re.S)


def looks_repetitive(text: str) -> bool:
    m = _LOOP.search(text)
    if not m:
        return False
    # 重複區塊要佔全文三成以上才判定異常，避免誤殺正常疊詞
    return (len(m.group(0)) / max(len(text), 1)) >= 0.3
