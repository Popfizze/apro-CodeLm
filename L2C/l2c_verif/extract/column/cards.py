from __future__ import annotations

import re

from ...geometry import lines_bbox
from ...ingest import normalize_level
from ...rebar import norm_text, parse_line
from ..base import Ctx, make_item
from .items import TYPE

RE_CARD_LOC = re.compile(r"COL\s*:\s*([A-Z]{1,2}(?:\.\d)?)\s*-\s*(\d{1,2}(?:\.\d)?)")
RE_CARD_LEVEL = re.compile(r"^(.+?)\s*:\s*\d{4,6}$")
RE_CARD_SPACING = re.compile(r"^(\d+)\s*@\s*(\d+)$")
BAR_LABELS = ("VERT", "ET")


def _card_lines(page, anchor: dict) -> list[dict]:
    x0, y0 = anchor["bbox"][0], anchor["bbox"][1]
    return [
        ln
        for ln in page.lines
        if x0 - 8 <= ln["bbox"][0] <= x0 + 320 and y0 - 35 <= ln["bbox"][1] <= y0 + 600
    ]


def _text_rows(card: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    horizontal = sorted(
        (ln for ln in card if ln["dir"] == (1, 0)), key=lambda ln: (ln["bbox"][1], ln["bbox"][0])
    )
    for ln in horizontal:
        if rows and abs(rows[-1][0]["bbox"][1] - ln["bbox"][1]) < 4:
            rows[-1].append(ln)
        else:
            rows.append([ln])
    return rows


def _row_text(row: list[dict]) -> str:
    return " ".join(norm_text(ln["text"]) for ln in sorted(row, key=lambda ln: ln["bbox"][0]))


def _card_level(rows: list[list[dict]], texts: list[str]) -> str | None:
    levels = []
    for row, text in zip(rows, texts, strict=True):
        match = RE_CARD_LEVEL.match(text)
        level = normalize_level(match.group(1)) if match and not text.startswith("PROJECT") else None
        if level:
            levels.append((row[0]["bbox"][1], level))
    if not levels:
        return None
    level = max(levels)[1]
    return "SOUS-SOL" if level == "FONDATION" else level


def _tie_spacing(card: list[dict]):
    return next(
        (
            RE_CARD_SPACING.match(norm_text(ln["text"]))
            for ln in card
            if ln["dir"] != (1, 0) and RE_CARD_SPACING.match(norm_text(ln["text"]))
        ),
        None,
    )


def _card_bars(card: list[dict], texts: list[str]) -> list:
    bars = [bar for text in texts if text.startswith(BAR_LABELS) for bar in parse_line(text)]
    spacing = _tie_spacing(card)
    for bar in bars:
        if bar.role == "LIG" and spacing and bar.espacement_mm is None:
            bar.espacement_mm = float(spacing.group(2))
    return bars


def _card_item(ctx: Ctx, page, anchor: dict):
    card = _card_lines(page, anchor)
    rows = _text_rows(card)
    texts = [_row_text(row) for row in rows]
    location = next((RE_CARD_LOC.search(t) for t in texts if RE_CARD_LOC.search(t)), None)
    level = _card_level(rows, texts) if location else None
    if level is None:
        return None
    bars = _card_bars(card, texts)
    if not bars:
        return None
    loc = f"{location.group(1)}-{location.group(2)}"
    used = [ln for row, text in zip(rows, texts, strict=True) if text.startswith(BAR_LABELS) for ln in row]
    return make_item(
        ctx,
        page,
        id=f"{page.key}_{loc}_{level}",
        type_element=TYPE,
        bbox=lines_bbox(used),
        armature=bars,
        read={"armature": bars, "confiance": 0.8, "methode": "regex"},
        element=loc,
        niveau=level,
        localisation=loc,
        texte_brut=" / ".join(texts),
    )


def axis_cards(ctx: Ctx, page) -> list:
    anchors = [ln for ln in page.lines if norm_text(ln["text"]).startswith("AXE")]
    return [item for item in (_card_item(ctx, page, anchor) for anchor in anchors) if item is not None]
