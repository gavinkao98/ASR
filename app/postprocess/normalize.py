import re

_CJK = re.compile(r"[一-鿿㐀-䶿]")
_MAP = {",": "，", ".": "。", "?": "？", "!": "！", ";": "；", ":": "："}


def _cjk_ratio(text: str) -> float:
    stripped = re.sub(r"\s", "", text)
    if not stripped:
        return 0.0
    return len(_CJK.findall(stripped)) / len(stripped)


def normalize_punct(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # 低於此比例視為英文句、維持半形標點。門檻取 0.25（非計畫原稿的 0.3）：
    # 夾雜長英文術語的中文句 CJK 佔比會被拉低（例 "我們用faster-whisper跑,很快!" 僅 0.27），
    # 仍須依 spec §4 判為中文句套全形標點；此值同時讓純英文句（0 佔比）維持半形。
    if _cjk_ratio(text) < 0.25:
        return text
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch not in _MAP:
            continue
        prev = chars[i - 1] if i > 0 else ""
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        # 兩側皆英數 → 視為英文語境（小數點、網址等），不轉
        if prev.isascii() and prev.isalnum() and nxt.isascii() and nxt.isalnum():
            continue
        chars[i] = _MAP[ch]
    # 全形標點後的殘留空格清掉（"你好， 世界" → "你好，世界"）
    return re.sub(r"([，。？！；：])\s+", r"\1", "".join(chars))
