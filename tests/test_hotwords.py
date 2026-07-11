from app.postprocess.hotwords import parse_rules, apply_rules


def test_parse_skips_comments_and_blank():
    text = "# 註解\n卡斯騰=Custom\n\n派森=Python\n"
    assert parse_rules(text) == [("卡斯騰", "Custom"), ("派森", "Python")]


def test_apply_longest_first():
    rules = parse_rules("派森=Python\n派森腳本=Python script\n")
    assert apply_rules("我寫了派森腳本", rules) == "我寫了Python script"


def test_apply_multiple_occurrences():
    rules = parse_rules("欸皮愛=API\n")
    assert apply_rules("這個欸皮愛跟那個欸皮愛", rules) == "這個API跟那個API"


def test_malformed_lines_ignored():
    assert parse_rules("沒有等號這行\n好=good\n") == [("好", "good")]
