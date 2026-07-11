"""Qwen3-ASR GGUF 輸出包裝解析（純函式，不需下載模型，恆執行）。"""
from app.engines.qwen3 import _extract_asr_text


def test_extract_strips_language_and_asr_text_wrapper():
    assert _extract_asr_text("language Chinese<asr_text>今天天氣很好。") == "今天天氣很好。"


def test_extract_empty_when_no_speech():
    # 無語音時模型回 'language None<asr_text>'（內容為空）
    assert _extract_asr_text("language None<asr_text>") == ""


def test_extract_handles_optional_closing_tag():
    assert _extract_asr_text("language Chinese<asr_text>你好</asr_text>") == "你好"


def test_extract_passthrough_without_wrapper():
    # 萬一未來版本不帶包裝，原樣回傳（去頭尾空白）
    assert _extract_asr_text("  純文字  ") == "純文字"
