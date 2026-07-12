"""中文數字→阿拉伯數字（規則式、零依賴）。設計：specs/2026-07-12-digits-to-arabic。

兩套規則並行：
①「連續 ≥3 個純數字字」整串逐字轉（四零九六→4096）——電話、代號、年份的念法。
②「含位值字（十百千萬億）且緊接數值單位」才轉（十二GB→12GB）——嚴格位值解析，
  digit-digit（四五十＝約數）、升位（一千二千）等不合法序列一律不動。
寧可不轉，不可轉錯：成語（十全十美）、慣用語（一定、萬一）、約數（五六個）
因不符合兩規則的結構條件而天然保留。
"""
import re

# ---- 規則 1：連續數字串逐字轉 ----
_D2A = str.maketrans("零〇一二三四五六七八九", "00123456789")
_RUN = re.compile(r"[零〇一二三四五六七八九]{3,}")

# ---- 規則 2：位值＋單位 ----
_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
          "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_UNIT = {"十": 10, "百": 100, "千": 1000}
_SECTION = {"萬": 10_000, "億": 100_000_000}
_HAS_PLACE = re.compile(r"[十百千萬億]")
# 數值單位表：刻意不含通用量詞（個/種/次/位）與單字「分」（避開「十分感謝」）。
# 英文單位加 (?![A-Za-z]) 防止吃到 GBP 這類更長縮寫；字母間容忍一個空白
# （ASR 會把字母拆開唸寫成「G B」），數值與單位之間亦然，輸出時收乾淨。
_UNITS = (r"公斤|公克|公尺|公里|公分|分鐘|小時|[GgMmKkTt]\s?[Bb](?![A-Za-z])|"
          r"趴|元|塊|度|倍|秒|天|日|年|月|週|歲|號")
_VALUE_UNIT = re.compile(
    r"([零〇一二兩三四五六七八九十百千萬億]+)\s?(" + _UNITS + ")")


def _pad_ascii_digits(m: re.Match, converted: str) -> str:
    """轉換結果緊貼既有阿拉伯數字時補一個空格，避免黏成一個大數字（407012GB）。"""
    s = m.string
    before = s[m.start() - 1] if m.start() > 0 else ""
    after = s[m.end()] if m.end() < len(s) else ""
    if before.isascii() and before.isdigit():
        converted = " " + converted
    if after.isascii() and after.isdigit():
        converted = converted + " "
    return converted


def _parse(expr: str) -> int | None:
    """嚴格位值解析：合法中文數字回整數值，任何可疑序列回 None（呼叫端不轉）。"""
    total = 0            # 已收斂的分節（萬/億）
    section = 0          # 目前分節內已定值
    num = 0              # 待掛位的數字
    has_num = False
    last_unit: int | None = None      # 分節內上一個位值，強制遞減
    last_section: int | None = None   # 上一個分節位值，強制遞減
    tail_base: int | None = None      # 口語省位基準（一百二→2×10）
    after_zero = False
    started = False      # 「十」開頭（十二=12）只允許在整串開頭
    for ch in expr:
        if ch in _DIGIT:
            if has_num:
                return None           # digit-digit（四五十）＝約數，拒絕
            if ch in ("零", "〇"):
                after_zero = True     # 零只占位，不成為待掛數字
            else:
                num = _DIGIT[ch]
                has_num = True
            started = True
        elif ch in _UNIT:
            mag = _UNIT[ch]
            if last_unit is not None and mag >= last_unit:
                return None           # 升位（一千二千）拒絕
            if not has_num:
                if ch == "十" and not started:
                    num = 1           # 前導十：十二=12
                else:
                    return None       # 「百元」「三萬十」這類缺前導數字，拒絕
            section += num * mag
            num, has_num = 0, False
            last_unit = mag
            tail_base = mag // 10
            after_zero = False
            started = True
        elif ch in _SECTION:
            mag = _SECTION[ch]
            if last_section is not None and mag >= last_section:
                return None
            if section == 0 and not has_num:
                return None           # 「萬一」的萬無前導，拒絕
            total += (section + num) * mag
            section, num, has_num = 0, 0, False
            last_unit = None
            last_section = mag
            tail_base = mag // 10_000 * 1000 if mag >= 10_000 else None
            after_zero = False
            started = True
        else:                          # 字集外（理論上 regex 擋掉了）
            return None
    if has_num:
        if after_zero or tail_base in (None, 0):
            section += num             # 一百零五=105；或無省位基準時直加
        else:
            section += num * tail_base  # 一百二=120、三萬五=35000、十二=12
    return total + section


def _sub_value_unit(m: re.Match) -> str:
    expr, unit = m.group(1), m.group(2)
    if not _HAS_PLACE.search(expr):
        return m.group(0)              # 無位值字（五元）不在規則 2 範圍
    value = _parse(expr)
    if value is None:
        return m.group(0)
    unit = re.sub(r"\s", "", unit)     # 「G B」→「GB」
    return _pad_ascii_digits(m, str(value) + ("%" if unit == "趴" else unit))


def to_arabic(text: str) -> str:
    """先逐字轉連續數字串，再處理位值＋單位（順序固定：規則 1 清掉的長串
    不會再被規則 2 的貪婪匹配吃進位值表達式）。"""
    text = _RUN.sub(
        lambda m: _pad_ascii_digits(m, m.group().translate(_D2A)), text)
    return _VALUE_UNIT.sub(_sub_value_unit, text)
