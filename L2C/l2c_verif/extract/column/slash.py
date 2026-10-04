from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

from ...geometry import center, lines_bbox
from ...rebar import norm_text
from ..base import Ctx
from .bars import (
    RE_SHOP_BAR,
    RE_VERTICAL_SPACING,
    in_spacing_range,
    reading_confidence,
    section_area,
    shop_bars,
    unread_segments,
)
from .items import ocr_item
from .labels import horizontal_lines, location_fixed, normalize_location

RE_SLASH_HEAD = re.compile(r"^([A-Z0-9]{1,2}(?:\.\d)?)/([A-Z0-9]{1,2}(?:\.\d)?)$")
RE_SLASH_MISREAD = re.compile(r"^([A-Z]{1,2}(?:\.\d)?)[LI1|]([0-9OIL]{1,2}(?:\.\d)?)$")
RE_CARD_LABEL = re.compile(r"^(VERT|ET)\b\s*[.:;,\-{]*\s*")
DEFAULT_PITCH = (210.0, 390.0)


@dataclass
class _Reading:
    bars: list = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    used: list[dict] = field(default_factory=list)
    unread: int = 0


def _is_horizontal(ln: dict) -> bool:
    return tuple(ln["dir"]) == (1, 0)


def _slash_headers(page) -> list[tuple]:
    lines = horizontal_lines(page)
    quantities = [ln for ln in lines if norm_text(ln["text"]).startswith("QTE")]
    heads = []
    for ln in lines:
        compact = norm_text(ln["text"]).replace(" ", "")
        match = RE_SLASH_HEAD.match(compact) or RE_SLASH_MISREAD.match(compact)
        if not match:
            continue
        cy = center(ln["bbox"])[1]
        if any(
            abs(center(q["bbox"])[1] - cy) <= 15 and 0 < q["bbox"][0] - ln["bbox"][2] <= 250
            for q in quantities
        ):
            heads.append((match.group(1), match.group(2), ln["bbox"]))
    return heads


def _rows_of(heads: list[tuple], tolerance: float) -> list[list]:
    rows: list[list] = []
    for head in sorted(heads, key=lambda h: h[2][1]):
        if rows and head[2][1] - rows[-1][0][2][1] <= tolerance:
            rows[-1].append(head)
        else:
            rows.append([head])
    return rows


def _next_gap(heads: list[tuple], box, axis: int) -> float | None:
    across = 1 - axis
    return min(
        (
            o[2][axis] - box[axis]
            for o in heads
            if o[2][axis] > box[axis] + 20 and abs(o[2][across] - box[across]) <= 20
        ),
        default=None,
    )


def _pitches(heads: list[tuple]) -> tuple[float, float]:
    x_gaps = [_next_gap(heads, h[2], 0) for h in heads]
    y_gaps = [_next_gap(heads, h[2], 1) for h in heads]
    return (
        median([g for g in x_gaps if g] or [DEFAULT_PITCH[0]]),
        median([g for g in y_gaps if g] or [DEFAULT_PITCH[1]]),
    )


def _card_lines(page, heads: list[tuple], box, pitch: tuple[float, float]) -> list[dict]:
    left, top = box[0] - 15, box[1] - 10
    right = min(
        (h[2][0] - 15 for h in heads if h[2][0] > box[0] + 5 and abs(h[2][1] - box[1]) <= 20),
        default=left + pitch[0],
    )
    bottom = min(
        (h[2][1] - 10 for h in heads if h[2][1] > box[1] + 20 and abs(h[2][0] - box[0]) <= pitch[0] / 2),
        default=top + pitch[1],
    )
    return [
        ln
        for ln in page.lines
        if left <= center(ln["bbox"])[0] < right and top <= center(ln["bbox"])[1] < bottom
    ]


def _card_text(card: list[dict], label_line: dict) -> tuple[str, list[dict]]:
    x0, y0, x1, y1 = label_line["bbox"]
    height = max(y1 - y0, 1.0)
    parts, used = [RE_CARD_LABEL.sub("", norm_text(label_line["text"]))], [label_line]
    for ln in sorted(card, key=lambda ln: (ln["bbox"][1], ln["bbox"][0])):
        if ln is label_line or not _is_horizontal(ln) or RE_CARD_LABEL.match(norm_text(ln["text"])):
            continue
        cy = center(ln["bbox"])[1]
        if ln["bbox"][0] >= min(x1 - 3, x0 + 2 * height) and y0 - height <= cy <= y1 + height:
            parts.append(norm_text(ln["text"]))
            used.append(ln)
    return " | ".join(p for p in parts if p), used


def _guessed_bars(text: str, roles: set[str], area: float | None) -> list[tuple]:
    guesses = []
    if "VERT" in roles:
        guesses += [
            (bar, f"VERT? {text}") for bar, _ in shop_bars(text, "VERT", True, area) if bar.diametre != "10M"
        ]
    if "LIG" in roles:
        guesses += [(bar, f"ET? {text}") for bar, _ in shop_bars(text, "LIG", False) if bar.diametre == "10M"]
    return guesses


def _unlabeled_bars(card: list[dict], reading: _Reading, area: float | None, roles: set[str]) -> None:
    taken = {id(ln) for ln in reading.used}
    for ln in sorted(card, key=lambda ln: ln["bbox"][1]):
        text = norm_text(ln["text"])
        if id(ln) in taken or not _is_horizontal(ln) or not RE_SHOP_BAR.search(text):
            continue
        for bar, label in _guessed_bars(text, roles, area):
            reading.bars.append((bar, False))
            reading.texts.append(label)


def _labeled_bars(card: list[dict], area: float | None) -> _Reading:
    reading = _Reading()
    for ln in card:
        match = RE_CARD_LABEL.match(norm_text(ln["text"]))
        if not match or not _is_horizontal(ln):
            continue
        text, used = _card_text(card, ln)
        reading.used.extend(used)
        role = "VERT" if match.group(1) == "VERT" else "LIG"
        reading.bars.extend(shop_bars(text, role, role == "VERT", area))
        reading.unread += unread_segments(text, role) if role == "VERT" else 0
        reading.texts.append(f"{match.group(1)}: {text}")
    return reading


def _apply_tie_spacing(card: list[dict], bars: list) -> None:
    matches = (
        RE_VERTICAL_SPACING.match(norm_text(ln["text"]).replace(" ", ""))
        for ln in card
        if not _is_horizontal(ln)
    )
    spacings = {int(m.group(2)) for m in matches if m}
    if len(spacings) != 1:
        return
    value = float(spacings.pop())
    if in_spacing_range(value):
        for bar in bars:
            if bar.role == "LIG" and bar.espacement_mm is None:
                bar.espacement_mm = value


def _card_area(card: list[dict]) -> float | None:
    return next(
        (
            section_area(ln["text"])
            for ln in card
            if norm_text(ln["text"]).startswith("DIM") and section_area(ln["text"])
        ),
        None,
    )


def _slash_item(ctx: Ctx, page, head: tuple, card: list[dict], loc: str, level: str):
    letter, number, box = head
    area = _card_area(card)
    reading = _labeled_bars(card, area)
    missing_roles = {"VERT", "LIG"} - {a.role for a, _ in reading.bars}
    if missing_roles:
        _unlabeled_bars(card, reading, area, missing_roles)
    bars = [a for a, _ in reading.bars]
    _apply_tie_spacing(card, bars)
    framed = reading.used or [ln for ln in card if ln["bbox"][1] > box[3] + 5] or card
    confidence = reading_confidence(reading.bars, location_fixed(letter, number, loc), reading.unread)
    raw = f"{letter}/{number}: " + " / ".join(reading.texts)
    return ocr_item(ctx, page, loc, level, lines_bbox(framed), bars, raw, confidence)


def slash_cards(ctx: Ctx, page, labels, level: str, preferred=None) -> list:
    heads = _slash_headers(page)
    if not heads:
        return []
    pitch = _pitches(heads)
    items = []
    for row in _rows_of(heads, 15.0):
        for head in row:
            card = _card_lines(page, heads, head[2], pitch)
            loc = normalize_location(head[0], head[1], labels, preferred)
            if loc is not None:
                items.append(_slash_item(ctx, page, head, card, loc, level))
    return items
