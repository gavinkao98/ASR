from app.postprocess.chain import build_chain


def fake_punct(text):
    return text + "。"


def test_breeze_like_chain_adds_punct_and_hotwords(tmp_path):
    hw = tmp_path / "hotwords.txt"
    hw.write_text("派森=Python", encoding="utf-8")
    chain = build_chain(has_punct=False, outputs_simplified=False,
                        use_punct_model=True, punct_fn=fake_punct, hotwords_path=hw)
    assert chain("我在學派森") == "我在學Python。"


def test_qwen3_like_chain_tradifies(tmp_path):
    chain = build_chain(has_punct=True, outputs_simplified=True,
                        use_punct_model=True, punct_fn=fake_punct,
                        hotwords_path=tmp_path / "none.txt")
    assert chain("我用软件,很好.") == "我用軟體，很好。"


def test_punct_model_skipped_when_disabled(tmp_path):
    chain = build_chain(has_punct=False, outputs_simplified=False,
                        use_punct_model=False, punct_fn=fake_punct,
                        hotwords_path=tmp_path / "none.txt")
    assert chain("測試") == "測試"


def test_verbatim_keeps_punct_but_skips_hotwords_and_normalize(tmp_path):
    # 原樣輸出：保留自動標點（fake_punct 補「。」），但不套熱詞（派森不變）、不做全形正規化
    hw = tmp_path / "hotwords.txt"
    hw.write_text("派森=Python", encoding="utf-8")
    chain = build_chain(has_punct=False, outputs_simplified=False,
                        use_punct_model=True, punct_fn=fake_punct,
                        hotwords_path=hw, verbatim=True)
    assert chain("我在學派森") == "我在學派森。"


def test_verbatim_keeps_tradify_but_not_fullwidth(tmp_path):
    # 原樣輸出仍簡轉繁（軟體），但半形逗號／句號不轉全形、不清空白
    chain = build_chain(has_punct=True, outputs_simplified=True,
                        use_punct_model=True, punct_fn=fake_punct,
                        hotwords_path=tmp_path / "none.txt", verbatim=True)
    assert chain("我用软件,很好.") == "我用軟體,很好."


def test_verbatim_defaults_off(tmp_path):
    # 不傳 verbatim＝一般模式，行為與現況相同（會套熱詞與全形正規化）
    hw = tmp_path / "hotwords.txt"
    hw.write_text("派森=Python", encoding="utf-8")
    chain = build_chain(has_punct=False, outputs_simplified=False,
                        use_punct_model=True, punct_fn=fake_punct, hotwords_path=hw)
    assert chain("我在學派森") == "我在學Python。"


def test_short_utterance_skips_punct_breeze(tmp_path):
    # Breeze 短句（< 門檻）跳過自動標點（fake_punct 不會補「。」）
    chain = build_chain(has_punct=False, outputs_simplified=False, use_punct_model=True,
                        punct_fn=fake_punct, hotwords_path=tmp_path / "none.txt",
                        punct_min_chars=10)
    assert chain("測試") == "測試"


def test_long_utterance_gets_punct_breeze(tmp_path):
    # 12 個中文字 ≥ 10 → 照常加標點
    chain = build_chain(has_punct=False, outputs_simplified=False, use_punct_model=True,
                        punct_fn=fake_punct, hotwords_path=tmp_path / "none.txt",
                        punct_min_chars=10)
    assert chain("今天天氣很好我想出去走走") == "今天天氣很好我想出去走走。"


def test_short_utterance_strips_qwen_native_punct(tmp_path):
    # Qwen 自帶標點，短句把它加的標點去掉（簡轉繁仍生效）
    chain = build_chain(has_punct=True, outputs_simplified=True, use_punct_model=True,
                        punct_fn=fake_punct, hotwords_path=tmp_path / "none.txt",
                        punct_min_chars=10)
    assert chain("你好，世界。") == "你好世界"


def test_english_counts_as_words_not_letters(tmp_path):
    # 「打開 Google Chrome」= 打開(2)+Google+Chrome = 4 單位 < 10 → 短句、不加標點
    chain = build_chain(has_punct=False, outputs_simplified=False, use_punct_model=True,
                        punct_fn=fake_punct, hotwords_path=tmp_path / "none.txt",
                        punct_min_chars=10)
    assert chain("打開 Google Chrome") == "打開 Google Chrome"


def test_short_keeps_internal_decimal(tmp_path):
    # 短句去標點時，句中的半形小數點要保留（不可把 3.14 弄成 314）
    chain = build_chain(has_punct=True, outputs_simplified=False, use_punct_model=True,
                        punct_fn=fake_punct, hotwords_path=tmp_path / "none.txt",
                        punct_min_chars=10)
    assert chain("圓周率3.14") == "圓周率3.14"


def test_punct_min_chars_zero_disables(tmp_path):
    # 0 = 關閉此功能：一律照常加標點
    chain = build_chain(has_punct=False, outputs_simplified=False, use_punct_model=True,
                        punct_fn=fake_punct, hotwords_path=tmp_path / "none.txt",
                        punct_min_chars=0)
    assert chain("測試") == "測試。"
