from __future__ import annotations

import re

from ...ingest import normalize_level
from ...rebar import norm_text

RE_LEVEL_NUMBER = re.compile(r"\bNIV(?:EAU)?\.?\s*(\d+)")
RE_BASEMENT = re.compile(r"SOUS.?SOL")
RE_ELEVATION_MARK = re.compile(r"^EL\.?\s*:")
RE_WALL_TITLE = re.compile(r"^ELEVATION\s*-?\s*MUR\s+([A-Z0-9.]{1,4})\b")
RE_TITLE_LETTER = re.compile(r"[A-Z]{1,2}\d?")
RE_GRID = re.compile(r"^(?:[A-Z]{1,2}(?:\.\d{1,2})?|\d{1,2}(?:\.\d{1,2})?)$")
SHORT_LEVELS = [
    (re.compile(r"REZ.?DE.?CHAUSSEE|^RDC$"), "RDC"),
    (re.compile(r"\bTOIT\b"), "TOIT"),
]
LEVEL_COLUMN_GAP = 80.0


def _basement_short(text: str) -> str:
    number = re.search(r"\bS?(\d)\b", text.split("SOL", 1)[1])
    return f"SS{number.group(1)}" if number else "SS"


def short_level(label: str) -> str:
    t = norm_text(label)
    number = RE_LEVEL_NUMBER.search(t)
    if number:
        return number.group(1)
    for word in ("TREFOND", "APPENTIS"):
        if word in t:
            return word
    if RE_BASEMENT.search(t):
        return _basement_short(t)
    fixed = next((level for pattern, level in SHORT_LEVELS if pattern.search(t)), None)
    return fixed or re.sub(r"\s*-\s*", "-", t)


def canonical_level(label: str) -> str:
    t = norm_text(label)
    if "TREFOND" in t:
        return "TREFOND"
    if RE_BASEMENT.search(t):
        short = short_level(t)
        return "SOUS-SOL" + ("" if short == "SS" else " " + short[2:])
    return normalize_level(t) or t


def _is_horizontal(ln: dict) -> bool:
    return ln["dir"] == (1, 0)


def _label_below(lines: list[dict], mark: dict) -> dict | None:
    x0, y1 = mark["bbox"][0], mark["bbox"][3]
    below = [
        ln
        for ln in lines
        if ln is not mark
        and abs(ln["bbox"][0] - x0) < 3
        and abs(ln["bbox"][1] - y1) < 5
        and _is_horizontal(ln)
        and len(ln["text"]) <= 30
    ]
    return below[0] if below else None


def elevation_levels(lines: list[dict]) -> list[tuple]:
    out = []
    for mark in lines:
        if not RE_ELEVATION_MARK.match(norm_text(mark["text"])) or not _is_horizontal(mark):
            continue
        label = _label_below(lines, mark)
        if label is None or RE_ELEVATION_MARK.match(norm_text(label["text"])):
            continue
        out.append(
            (short_level(label["text"]), canonical_level(label["text"]), label["bbox"][1], mark["bbox"][0])
        )
    return out


def _level_column(levels: list[tuple], x: float) -> list[tuple]:
    if not levels:
        return []
    columns: list[list] = []
    for level in sorted(levels, key=lambda lv: lv[3]):
        if columns and level[3] - columns[-1][-1][3] < LEVEL_COLUMN_GAP:
            columns[-1].append(level)
        else:
            columns.append([level])
    left = [c for c in columns if c[0][3] < x]
    column = left[-1] if left else min(columns, key=lambda c: abs(c[0][3] - x))
    return sorted(column, key=lambda lv: lv[2])


def band(levels: list[tuple], x: float, y: float) -> tuple:
    column = _level_column(levels, x)
    lower = next((lv for lv in column if lv[2] > y), None)
    upper = next((lv for lv in reversed(column) if lv[2] < y), None)
    return lower, upper


def _letter_left_of(lines: list[dict], title: dict) -> dict | None:
    x0, y0, _, y1 = title["bbox"]
    letters = [
        c
        for c in lines
        if RE_TITLE_LETTER.fullmatch(norm_text(c["text"]))
        and c["size"] >= title["size"] * 1.3
        and -5 <= x0 - c["bbox"][2] <= 80
        and c["bbox"][1] < y1 + 10
        and c["bbox"][3] > y0 - 10
    ]
    return min(letters, key=lambda c: x0 - c["bbox"][2]) if letters else None


def _title(lines: list[dict], ln: dict) -> tuple | None:
    text = norm_text(ln["text"])
    x0, y0, x1, _ = ln["bbox"]
    named = RE_WALL_TITLE.match(text)
    if named and ln["size"] >= 11:
        return (named.group(1), (x0 + x1) / 2, y0)
    if text != "ELEVATION" or ln["size"] < 11:
        return None
    letter = _letter_left_of(lines, ln)
    if letter is None:
        return None
    return (norm_text(letter["text"]), (letter["bbox"][0] + letter["bbox"][2]) / 2, letter["bbox"][1])


def elevation_titles(lines: list[dict]) -> list[tuple]:
    return [title for title in (_title(lines, ln) for ln in lines) if title is not None]


def grid_bubbles(lines: list[dict]) -> list[tuple]:
    return [
        ((ln["bbox"][0] + ln["bbox"][2]) / 2, ln["bbox"][1], norm_text(ln["text"]))
        for ln in lines
        if ln["size"] >= 14 and _is_horizontal(ln) and RE_GRID.match(norm_text(ln["text"]))
    ]
