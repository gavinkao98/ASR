import re
from typing import Callable

from app.postprocess.digits import to_arabic
from app.postprocess.hotwords import apply_rules, load_rules
from app.postprocess.normalize import normalize_punct
from app.postprocess.tradify import to_taiwan

_CJK = re.compile(r"[一-鿿㐀-䶿]")
_WORD = re.compile(r"[A-Za-z0-9]+")
_FULL_SENT_PUNCT = "。，、！？；："   # 全形句子標點；不會出現在數字/網址，短句可整串安全移除


def _content_units(text: str) -> int:
    """句子「長度」：中文一字算一個、英文一個單字算一個（不計標點與空白）。
    這樣「打開 Google Chrome」算 4，不會因為英文字母多被誤判成長句。"""
    return len(_CJK.findall(text)) + len(_WORD.findall(text))


def _strip_sentence_punct(text: str) -> str:
    """短句去標點：全形句子標點整串去掉；半形標點只去結尾殘留（保留 3.14、12:30 這類）。"""
    text = "".join(c for c in text if c not in _FULL_SENT_PUNCT)
    return re.sub(r"[.,!?;:]+$", "", text).strip()


def build_chain(*, has_punct: bool, outputs_simplified: bool,
                use_punct_model: bool, punct_fn: Callable[[str], str],
                hotwords_path, verbatim: bool = False,
                punct_min_chars: int = 0,
                digits_to_arabic: bool = True) -> Callable[[str], str]:
    def run(text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        # 短句（長度低於門檻）不加標點：Breeze 直接跳過標點模型；Qwen 自帶標點則稍後去掉。
        # punct_min_chars=0 代表關閉此功能、一律照常加標點。
        short = 0 < punct_min_chars and _content_units(text) < punct_min_chars
        if not has_punct and use_punct_model and not short:
            text = punct_fn(text)
        if outputs_simplified:
            text = to_taiwan(text)
        if short:
            text = _strip_sentence_punct(text)
        if verbatim:
            # 原樣輸出：保留自動標點與簡轉繁，但跳過熱詞替換與全形標點正規化，
            # 盡量照抄辨識模型吐出的文字（模型本身的語句整理無法在此關閉）。
            return text
        if digits_to_arabic:
            # 位置：簡→繁之後（digits 的字集是繁體）、熱詞之前（熱詞可反向覆蓋）
            text = to_arabic(text)
        text = apply_rules(text, load_rules(hotwords_path))  # 每次重讀＝即存即生效
        return normalize_punct(text)

    return run
