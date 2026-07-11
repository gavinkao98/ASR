from app.history import History


def test_add_and_list(tmp_path):
    h = History(tmp_path / "h.db")
    h.add("你好世界", "breeze")
    rows = h.list(10)
    assert rows[0]["text"] == "你好世界" and rows[0]["engine"] == "breeze"
    assert "ts" in rows[0]


def test_prune_to_200(tmp_path):
    h = History(tmp_path / "h.db")
    for i in range(230):
        h.add(f"第{i}句", "breeze")
    rows = h.list(500)
    assert len(rows) == 200
    assert rows[0]["text"] == "第229句"  # 最新在前


def test_clear(tmp_path):
    h = History(tmp_path / "h.db")
    h.add("x", "breeze")
    h.clear()
    assert h.list(10) == []
