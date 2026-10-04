from __future__ import annotations

import re

from ..rebar import BAR_SIZES

LABELS = {"VERT", "ETRI", "ET", "EPIN", "LIG", "LONG", "TRAN", "TRANS", "GOUJ", "ATT", "DIM", "PEAU"}
BAR_DIGITS = str.maketrans(
    {"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "i": "1", "|": "1", "S": "5", "s": "5"}
)
NUMBER_DIGITS = str.maketrans({"O": "0", "o": "0", "S": "5", "s": "5"})
SHAPE_LETTER_READ_AS_DIGIT = {"7": "T", "2": "Z"}
SIZE_PREFIXES = "|".join(s[:2] for s in sorted(BAR_SIZES))
RE_MISREAD_SIZE = re.compile(r"([0-9OoDIli|Ss]{2})M")
RE_GLUED_SIZE = re.compile(rf"(\d{{1,2}})({SIZE_PREFIXES})M")
RE_SHAPE_DIGITS = re.compile(r"\d{6,}[.,]?|\d{3,}-\d{2}[.,]?")
RE_NUMBER = re.compile(r"([@(]?)([0-9OoSs]+)([\")]?)")
RE_FIRST_WORD = re.compile(r"^([^\s:]+?)(\.?:|\s)")
RE_LABEL_WORD = re.compile(r"[A-Za-z\]\[|\/]+")
RE_INCH_SPACING = re.compile(r"@\s*(\d{1,2})'(?!\s*-?\s*\d)")


def clean_word(text: str) -> str:
    t = text.replace("|", " ").replace("©", "@").replace("®", "@").replace("—", "-").replace("–", "-")
    t = re.sub(r"^[\[\]{}]+(?=\S*\d)|(?<=\d)[\[\]{}]+$", "", t.strip())
    t = re.sub(r"^-+(?=[A-Za-z]{2})", "", t)
    t = re.sub(r"^[^\w@(\"'#\-]+(?=\d)", "", t)
    return t.strip(" _~")


def _bar_size(token: str) -> str | None:
    match = RE_MISREAD_SIZE.fullmatch(token)
    if not match or match.group(1).isdigit():
        return None
    candidate = match.group(1).translate(BAR_DIGITS) + "M"
    return candidate if candidate in BAR_SIZES else None


def _glued_count(token: str) -> str | None:
    match = RE_GLUED_SIZE.fullmatch(token)
    return f"{match.group(1)} {match.group(2)}M" if match else None


def _shape_letter(token: str, previous: str | None) -> str | None:
    if previous not in BAR_SIZES or token[:2] != previous[:2] or len(token) <= 2:
        return None
    if token[2] not in SHAPE_LETTER_READ_AS_DIGIT or not RE_SHAPE_DIGITS.fullmatch(token):
        return None
    return token[:2] + SHAPE_LETTER_READ_AS_DIGIT[token[2]] + token[3:]


def _number(token: str) -> str | None:
    match = RE_NUMBER.fullmatch(token)
    if not match or not re.search(r"\d", match.group(2)):
        return None
    if sum(ch.isdigit() for ch in match.group(2)) * 2 < len(match.group(2)):
        return None
    return match.group(1) + match.group(2).translate(NUMBER_DIGITS) + match.group(3)


def _mark(token: str) -> str:
    token = re.sub(r"^[1Il|][Oo](?=[A-Z]{1,3}\d)", "10", token)
    token = re.sub(r"^([2-5])[Oo](?=[A-Z]{1,3}\d)", r"\g<1>0", token)
    return re.sub(r"(?<=\d)[Oo](?=\d)", "0", token)


def _fix_token(token: str, previous: str | None) -> str:
    fixed = _bar_size(token) or _glued_count(token) or _shape_letter(token, previous) or _number(token)
    return fixed if fixed is not None else _mark(token)


def fix_text(text: str) -> str:
    out: list[str] = []
    for token in text.split():
        out.extend(_fix_token(token, out[-1] if out else None).split())
    return RE_INCH_SPACING.sub(r'@\1"', " ".join(out))


def _within_one_edit(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) <= 1
    if len(a) > len(b):
        a, b = b, a
    return any(b[:i] + b[i + 1 :] == a for i in range(len(b)))


def _closest_label(word: str, text: str) -> str | None:
    key = re.sub(r"[^A-Z]", "", word.upper())
    followed_by_value = re.match(rf"^{re.escape(word)}\.?\s*(:|\d)", text)
    if len(word) < 3 or key in LABELS or not RE_LABEL_WORD.fullmatch(word) or not followed_by_value:
        return None
    return next(
        (
            label
            for label in LABELS
            if len(label) >= len(word) - 1 >= 2 and _within_one_edit(word.upper(), label)
        ),
        None,
    )


def fix_role_label(text: str) -> str:
    match = RE_FIRST_WORD.match(text + " ")
    if not match:
        return text
    word = match.group(1)
    label = _closest_label(word, text)
    if label:
        text = label + text[len(word) :]
        word = label
    if word.upper() not in LABELS:
        return text
    text = word.upper() + text[len(word) :]
    word = word.upper()
    return re.sub(rf"^{re.escape(word)}\.?\s+(?=\d{{1,3}}\s+\d{{2}}M\b)", word + ": ", text)
