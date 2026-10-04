from __future__ import annotations

import re
import unicodedata

from .models import Armature

INCH_MM = 25.4
BAR_SIZES = {"10M", "15M", "20M", "25M", "30M", "35M", "45M", "55M"}

RE_MILLIMETRES = re.compile(r"(\d+(?:\.\d+)?)\s*(MM)?")
RE_METRES = re.compile(r"(\d+(?:\.\d+)?)\s*M")
RE_FEET_INCHES = re.compile(
    r"(?:(?P<feet>\d+)\s*'\s*-?\s*)?(?:(?P<inches>\d+)(?:\s+(?P<num>\d+)/(?P<den>\d+))?\s*\"?)?"
)
RE_SPACING_VALUE = re.compile(
    r"(\d+\s*'\s*-?\s*\d*\s*\"?|\d+(?:\.\d+)?\s*\"|\d+(?:\.\d+)?\s*MM|\d+(?:\.\d+)?)"
)

ROLE_ALIASES = {
    "ARM": "VERT",
    "VERT": "VERT",
    "LIG": "LIG",
    "ETRI": "LIG",
    "ETR": "LIG",
    "ET": "LIG",
    "LONG": "LONG",
    "TRAN": "TRAN",
    "TRANS": "TRAN",
    "GOUJ": "GOUJ",
    "ATT": "ATT",
}

SPACING_PATTERN = r"@\s*(?P<spacing>\d+\s*'\s*-?\s*\d+\s*\"|\d+(?:\.\d+)?\s*(?:\"|MM)?)"
RE_SHOP_LINE = re.compile(
    r"^(?P<role>[A-Z]+)\.?\s*:\s*(?P<qty>\d+)\s*(?:X\s*\d+\s*)?(?P<size>\d{2}M)\s+"
    r"(?P<mark>[0-9]{2}[A-Z]+[0-9A-Z\-X]*)?\s*(?:" + SPACING_PATTERN + r")?"
)
RE_QTY_SIZE = re.compile(r"(?<![\d.])(?P<qty>\d+)\s*-\s*(?P<size>\d{2}M)\b")
RE_SIZE_SPACING = re.compile(r"(?<![\d-])(?P<size>\d{2}M)\s*" + SPACING_PATTERN)
RE_INTEG = re.compile(r"(?<![\d.])(?P<tot>\d+)\s*\(\s*(?P<per>\d+)\s*\)(?:\s*-\s*(?P<size>\d{2}M))?")
RE_ROLE_PREFIX = re.compile(r"^(?P<role>[A-Z][A-Z .]*?\d?)\s*\.?\s*:")
RE_BAR_SIZE = re.compile(r"(?<![\dA-Z])\d{2}M(?![A-Z])")


def strip_accents(text: str) -> str:
    text = text.replace("�", "E")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def norm_text(text: str) -> str:
    t = strip_accents(text).upper()
    t = t.replace("’", "'").replace("′", "'").replace("”", '"').replace("″", '"')
    t = t.replace("''", '"')
    return re.sub(r"\s+", " ", t).strip()


def _imperial_to_mm(match: re.Match, text: str) -> float:
    inches = int(match.group("inches") or 0)
    if match.group("num"):
        inches += int(match.group("num")) / int(match.group("den"))
    if match.group("feet") is None and '"' not in text and "'" not in text:
        return float(inches)
    return round((int(match.group("feet") or 0) * 12 + inches) * INCH_MM, 1)


def length_to_mm(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = norm_text(str(raw)).replace("C/C", "").strip()
    if not text:
        return None
    match = RE_MILLIMETRES.fullmatch(text)
    if match:
        return float(match.group(1))
    match = RE_METRES.fullmatch(text)
    if match:
        return float(match.group(1)) * 1000.0
    match = RE_FEET_INCHES.fullmatch(text)
    if match and (match.group("feet") or match.group("inches")):
        return _imperial_to_mm(match, text)
    return None


def spacing_to_mm(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = norm_text(str(raw)).replace("@", " ").replace("C/C", " ").strip()
    match = RE_SPACING_VALUE.match(text)
    return length_to_mm(match.group(1)) if match else None


def bar_size(text: str) -> str:
    return re.sub(r"\s+", "", text.upper())


def _role(name: str) -> str:
    key = re.sub(r"[^A-Z0-9 ]", "", name).strip()
    first = key.split(" ")[0] if key else key
    return ROLE_ALIASES.get(first, key)


def _shop_line_bar(match: re.Match) -> Armature:
    role = _role(match.group("role"))
    spacing = match.group("spacing")
    return Armature(
        role=role,
        repere=match.group("mark") or role,
        diametre=match.group("size"),
        quantite=int(match.group("qty")),
        espacement_mm=spacing_to_mm(spacing) if spacing else None,
    )


def _callout_bars(text: str) -> list[Armature]:
    prefix = RE_ROLE_PREFIX.match(text)
    role = _role(prefix.group("role")) if prefix else None
    bars = [
        Armature(role=role, repere=role, diametre=m.group("size"), quantite=int(m.group("qty")))
        for m in RE_QTY_SIZE.finditer(text)
        if m.group("size") in BAR_SIZES
    ]
    bars += [
        Armature(
            role=role, repere=role, diametre=m.group("size"), espacement_mm=spacing_to_mm(m.group("spacing"))
        )
        for m in RE_SIZE_SPACING.finditer(text)
        if m.group("size") in BAR_SIZES
    ]
    return bars


def _integrity_bars(text: str) -> list[Armature]:
    return [
        Armature(role="INTEG", repere="INTEG", diametre=m.group("size"), quantite=int(m.group("tot")))
        for m in RE_INTEG.finditer(text)
    ]


def parse_line(text: str) -> list[Armature]:
    t = norm_text(text)
    match = RE_SHOP_LINE.match(t)
    if match and match.group("size") in BAR_SIZES:
        return [_shop_line_bar(match)]
    return _callout_bars(t) or _integrity_bars(t)


def parse_lines(lines: list[str]) -> list[Armature]:
    return [armature for line in lines for armature in parse_line(line)]


def has_rebar(text: str) -> bool:
    t = norm_text(text)
    return bool(RE_BAR_SIZE.search(t) or (RE_INTEG.search(t) and "(" in t))


def mm_str(value: float | None) -> str | None:
    if value is None:
        return None
    inches = value / INCH_MM
    if abs(inches - round(inches)) < 0.05:
        return f'{round(value)} mm ({round(inches)}")'
    return f"{round(value)} mm"
