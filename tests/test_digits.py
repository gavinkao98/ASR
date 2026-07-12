"""中文數字→阿拉伯數字。案例多取自使用者真實辨識歷史（history.db）。
規則：①連續≥3個純數字字逐字轉；②含位值（十百千萬億）且緊接數值單位才轉，
嚴格解析、不合法一律不動。"""
import pytest

from app.postprocess.digits import to_arabic


# ---- 規則 1：連續數字串逐字轉 ----
@pytest.mark.parametrize("src,expect", [
    ("四零九六", "4096"),
    ("之前沒加入槓C四零九六。", "之前沒加入槓C4096。"),
    ("一二三四五六七", "1234567"),
    ("零九一二三四五六七八九", "09123456789"),      # 手機號碼，前導零保留
    ("二〇二四年", "2024年"),                        # 〇 也是數字字
])
def test_digit_runs_converted(src, expect):
    assert to_arabic(src) == expect


@pytest.mark.parametrize("src", [
    "四五",            # 兩個字不足門檻（約數）
    "第一個",
    "一定要用備份嗎",
    "有兩個問題",
    "這三項都正常",
    "千問三",          # 產品名
    "五六個人",
    "三四天",
])
def test_short_runs_and_idioms_untouched(src):
    assert to_arabic(src) == src


# ---- 規則 2：位值＋接單位才轉 ----
@pytest.mark.parametrize("src,expect", [
    ("十二GB", "12GB"),
    ("十二gb", "12gb"),                # 大小寫不影響數字轉換、單位原樣
    ("二十歲", "20歲"),
    ("一百趴", "100%"),                # 趴 → %
    ("一千兩百五十元", "1250元"),      # 兩=2
    ("三萬五千元", "35000元"),
    ("三萬五塊", "35000塊"),           # 口語省位
    ("一百零五元", "105元"),           # 零占位
    ("一百二元", "120元"),             # 口語省位
    ("一百五十元", "150元"),
    ("十秒", "10秒"),                  # 前導十
    ("二十一號", "21號"),
    ("十分鐘後", "10分鐘後"),
    ("兩百塊", "200塊"),
    ("一百二十三倍", "123倍"),
    ("三十天", "30天"),
    ("二十週", "20週"),
])
def test_place_value_with_unit_converted(src, expect):
    assert to_arabic(src) == expect


@pytest.mark.parametrize("src", [
    "四五十元",         # digit-digit＝約數 → 嚴格解析拒絕
    "五六十歲",
    "一千二千元",       # 升位不合法
    "十分感謝",         # 「分」不是單位（只認「分鐘」）
    "十全十美",
    "千方百計",
    "三十而立",
    "萬一發生問題",
    "萬眾一心",
    "一百二十",         # 無單位不轉（保守）
    "一年後",           # 無位值字，規則 2 前提不成立
    "三月",
    "五元",             # 單一數字字＋單位：不在兩規則範圍
])
def test_place_value_protected_or_out_of_scope(src):
    assert to_arabic(src) == src


# ---- 組合與邊界 ----
def test_mixed_sentence_from_history():
    assert (to_arabic("我有一張四零七零，十二GB的顯示卡。")
            == "我有一張4070，12GB的顯示卡。")


# ASR 會把字母單位拆開唸寫（「G B」）；單位比對容忍空白、輸出收乾淨
@pytest.mark.parametrize("src,expect", [
    ("十二G B", "12GB"),
    ("十二 GB", "12GB"),
    ("三十 M B", "30MB"),
])
def test_unit_letters_with_spaces(src, expect):
    assert to_arabic(src) == expect


# 轉換結果緊貼既有阿拉伯數字時補一個空格，避免黏成一個大數字（407012GB）
@pytest.mark.parametrize("src,expect", [
    ("我有一張4070十二G B的顯示卡。", "我有一張4070 12GB的顯示卡。"),
    ("4070四零九六", "4070 4096"),
    ("四零九六7080", "4096 7080"),
])
def test_space_inserted_next_to_ascii_digits(src, expect):
    assert to_arabic(src) == expect


def test_empty_and_ascii_passthrough():
    assert to_arabic("") == ""
    assert to_arabic("hello world 123") == "hello world 123"
