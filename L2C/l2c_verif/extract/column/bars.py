from __future__ import annotations

import re

from ...models import Armature
from ...rebar import BAR_SIZES, norm_text

RE_SHOP_BAR = re.compile(r"(?<![\w.@])(?:([0-9OIL]{1,2})\s*X\s*)?(\d{1,3})\s+(\d{2})\s?M(?![A-Z0-9])")
RE_SHOP_SPACING = re.compile(r"@\s*(\d{2,3})(?!\d)")
RE_SHOP_MARK = re.compile(r"^(\d{2})[A-Z]\d")
RE_MARK_FORMAT = re.compile(r"^\d{2}[A-Z0-9]{3,}")
RE_VERTICAL_SPACING = re.compile(r"^(\d{1,3})\s*@\s*(\d{2,3})$")
RE_SECTION = re.compile(r"(\d{3,4})\s*X\s*(\d{3,4})")
RE_ROUND_SECTION = re.compile(r"DIAM\.?\s*(\d{3,4})")
RE_REBAR_TRACE = re.compile(r"\d{2}\s?M\b|\b\d{2}[A-Z0-9]\d{3,}\b|^\W*\d{1,3}\s+\d{2}\b")
MAX_VERTICAL_BARS = 60
MAX_TIES = 200
SPACING_RANGE_MM = (50.0, 600.0)
MAX_STEEL_RATIO = 0.08
BAR_AREA_MM2 = {
    "10M": 100,
    "15M": 200,
    "20M": 300,
    "25M": 500,
    "30M": 700,
    "35M": 1000,
    "45M": 1500,
    "55M": 2500,
}


def section_area(text: str) -> float | None:
    t = norm_text(text)
    match = RE_SECTION.search(t)
    if match:
        return float(match.group(1)) * float(match.group(2))
    match = RE_ROUND_SECTION.search(t)
    if match:
        return 3.1416 * float(match.group(1)) ** 2 / 4
    return None


def in_spacing_range(value: float) -> bool:
    return SPACING_RANGE_MM[0] <= value <= SPACING_RANGE_MM[1]


def _noisy(tokens: list[str]) -> bool:
    return len(tokens) > 3 or any(len(tok) == 1 and tok != "@" for tok in tokens[1:])


def _plausible(size: str, quantity: int, vertical: bool, area: float | None) -> bool:
    if size not in BAR_SIZES or quantity <= 0 or quantity > (MAX_VERTICAL_BARS if vertical else MAX_TIES):
        return False
    return not (vertical and area and quantity * BAR_AREA_MM2[size] > MAX_STEEL_RATIO * area)


def _spacing(rest: str) -> float | None:
    match = RE_SHOP_SPACING.search(rest)
    value = float(match.group(1)) if match else None
    return value if value is not None and in_spacing_range(value) else None


def _shop_bar(segment: str, match: re.Match, role: str, vertical: bool, area: float | None):
    size, quantity = f"{match.group(3)}M", int(match.group(2))
    if not _plausible(size, quantity, vertical, area):
        return None
    rest = segment[match.end() :]
    tokens = rest.split()
    mark = tokens[0] if tokens else ""
    mark_size = RE_SHOP_MARK.match(mark)
    if mark_size and mark_size.group(1) != match.group(3):
        return None
    bar = Armature(
        role=role,
        repere=mark if RE_MARK_FORMAT.match(mark) else role,
        diametre=size,
        quantite=quantity,
        espacement_mm=_spacing(rest),
    )
    return bar, bool(mark_size) and not _noisy(tokens)


def shop_bars(text: str, role: str, vertical: bool, area: float | None = None) -> list[tuple[Armature, bool]]:
    out = []
    for segment in norm_text(text).split("|"):
        segment_role = "GOUJ" if "GOUJ" in segment else role
        for match in RE_SHOP_BAR.finditer(segment):
            reading = _shop_bar(segment, match, segment_role, vertical, area)
            if reading is not None:
                out.append(reading)
    return out


def unread_segments(text: str, role: str) -> int:
    return sum(
        1
        for segment in norm_text(text).split("|")
        if "GOUJ" not in segment
        and RE_REBAR_TRACE.search(segment)
        and not shop_bars(segment, role, role == "VERT")
    )


def reading_confidence(bars: list[tuple[Armature, bool]], location_fixed: bool, unread: int = 0) -> float:
    unverified = sum(1 for a, ok in bars if a.role == "VERT" and not ok)
    confidence = 0.8 - (0.1 if location_fixed else 0.0) - 0.1 * min(unverified, 2)
    return round(min(confidence, 0.6) if unread else confidence, 2)
