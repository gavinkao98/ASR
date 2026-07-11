from app.postprocess.normalize import normalize_punct


def test_chinese_sentence_gets_fullwidth():
    assert normalize_punct("你好,世界.") == "你好，世界。"


def test_pure_english_untouched():
    assert normalize_punct("Hello, world.") == "Hello, world."


def test_mixed_sentence_protects_number():
    assert normalize_punct("圓周率是3.14,記得嗎?") == "圓周率是3.14，記得嗎？"


def test_code_switch_keeps_fullwidth():
    assert normalize_punct("我們用faster-whisper跑,很快!") == "我們用faster-whisper跑，很快！"


def test_whitespace_cleanup():
    assert normalize_punct("  哈囉  世界  ") == "哈囉 世界"
