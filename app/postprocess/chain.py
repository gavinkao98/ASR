from typing import Callable

from app.postprocess.hotwords import apply_rules, load_rules
from app.postprocess.normalize import normalize_punct
from app.postprocess.tradify import to_taiwan


def build_chain(*, has_punct: bool, outputs_simplified: bool,
                use_punct_model: bool, punct_fn: Callable[[str], str],
                hotwords_path) -> Callable[[str], str]:
    def run(text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if not has_punct and use_punct_model:
            text = punct_fn(text)
        if outputs_simplified:
            text = to_taiwan(text)
        text = apply_rules(text, load_rules(hotwords_path))  # 每次重讀＝即存即生效
        return normalize_punct(text)

    return run
