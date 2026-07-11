def parse_rules(text: str) -> list[tuple[str, str]]:
    rules = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        wrong, _, right = line.partition("=")
        wrong, right = wrong.strip(), right.strip()
        if wrong and right:
            rules.append((wrong, right))
    return rules


def apply_rules(text: str, rules: list[tuple[str, str]]) -> str:
    for wrong, right in sorted(rules, key=lambda r: -len(r[0])):
        text = text.replace(wrong, right)
    return text


def load_rules(path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    return parse_rules(path.read_text(encoding="utf-8"))
