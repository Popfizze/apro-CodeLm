from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise

import fitz

from ...geometry import center, lines_bbox
from ...leaders import rotated_drawings
from ...rebar import norm_text
from ..base import Ctx
from ..frame import Frame
from .bars import RE_SHOP_BAR, RE_SHOP_SPACING, reading_confidence, section_area, shop_bars, unread_segments
from .items import ocr_item
from .labels import location_fixed, normalize_location

SCHEDULE_ROWS = ("COLONNE", "DIMENSION", "VERTICALE", "ETRIER")
RE_GRID_REF = re.compile(r"([A-Z0-9]{1,2}'?(?:\.\d{1,2})?)\s*-\s*([A-Z0-9]{1,2}(?:\.\d{1,2})?)")


@dataclass
class _Layout:
    frame: Frame
    lines: list[dict]
    rows: dict[str, dict]
    label_right: float
    bottom: float

    def y(self, name: str) -> float:
        return self.rows[name]["bbox"][1]


def _rule(p, q, min_len: float) -> tuple | None:
    if abs(p.x - q.x) < 1.0 and abs(p.y - q.y) >= min_len:
        return (p.x, min(p.y, q.y), p.x, max(p.y, q.y))
    if abs(p.y - q.y) < 1.0 and abs(p.x - q.x) >= min_len:
        return (min(p.x, q.x), p.y, max(p.x, q.x), p.y)
    return None


@lru_cache(maxsize=64)
def _long_rules(path: str, page_no: int, min_len: float) -> tuple:
    with fitz.open(path) as doc:
        drawings = rotated_drawings(doc[page_no - 1])
    rules = (_rule(item[1], item[2], min_len) for d in drawings for item in d["items"] if item[0] == "l")
    return tuple(rule for rule in rules if rule is not None)


def _is_horizontal(ln: dict) -> bool:
    return tuple(ln["dir"]) == (1, 0)


def _row_labels(lines: list[dict]) -> dict[str, dict]:
    found = {}
    for name in (*SCHEDULE_ROWS, "DETAIL"):
        labels = [ln for ln in lines if norm_text(ln["text"]) == name and _is_horizontal(ln)]
        if labels:
            found[name] = min(labels, key=lambda ln: ln["bbox"][0])
    return found


def _layout(page) -> _Layout | None:
    frame = Frame(page)
    lines = frame.lines(page.lines)
    rows = _row_labels(lines)
    if any(name not in rows for name in SCHEDULE_ROWS):
        return None
    if not rows["COLONNE"]["bbox"][1] < rows["DIMENSION"]["bbox"][1] < rows["VERTICALE"]["bbox"][1]:
        return None
    if not rows["VERTICALE"]["bbox"][1] < rows["ETRIER"]["bbox"][1]:
        return None
    label_right = max(rows[n]["bbox"][2] for n in SCHEDULE_ROWS)
    bottom = rows["DETAIL"]["bbox"][1] - 5 if "DETAIL" in rows else rows["ETRIER"]["bbox"][3] + 300
    return _Layout(frame, lines, rows, label_right, bottom)


def _column_rules(page, layout: _Layout) -> list[float]:
    top, bottom = layout.rows["COLONNE"]["bbox"][3], layout.y("ETRIER")
    boxes = [
        layout.frame.box(r)
        for r in _long_rules(str(page.path), page.page, (bottom - layout.y("COLONNE")) * 0.8)
    ]
    xs = sorted(
        {
            round(b[0])
            for b in boxes
            if b[2] - b[0] < 1.5 and b[0] > layout.label_right - 5 and b[1] <= top and b[3] >= bottom
        }
    )
    edges: list[float] = []
    for x in xs:
        if not edges or x - edges[-1] > 6:
            edges.append(x)
    return edges


def _headers(layout: _Layout) -> list[dict]:
    top, limit = layout.y("COLONNE") - 160, layout.y("DIMENSION") - 15
    return [
        ln
        for ln in layout.lines
        if ln["bbox"][0] > layout.label_right
        and top <= ln["bbox"][1] < limit
        and _is_horizontal(ln)
        and RE_GRID_REF.search(norm_text(ln["text"]))
    ]


def _cell_of(edges: list[float], ln: dict) -> int | None:
    x0, x1 = ln["bbox"][0], ln["bbox"][2]
    best = None
    for k, (a, b) in enumerate(pairwise(edges)):
        overlap = min(x1, b) - max(x0, a)
        if overlap > 0 and (best is None or overlap > best[0]):
            best = (overlap, k)
    return best[1] if best else None


def _fill_cell(cell: dict, ln: dict, layout: _Layout) -> None:
    cy = center(ln["bbox"])[1]
    if layout.y("VERTICALE") - 40 <= cy <= layout.bottom and RE_SHOP_BAR.search(norm_text(ln["text"])):
        cell["values"].append(ln)
    elif layout.y("DIMENSION") - 30 <= cy < layout.y("VERTICALE") - 20 and section_area(ln["text"]):
        cell["dims"].append(ln)


def _header_cells(heads: list[dict], edges: list[float]) -> dict[int, dict]:
    cells: dict[int, dict] = {}
    for head in sorted(heads, key=lambda ln: (ln["bbox"][1], ln["bbox"][0])):
        k = _cell_of(edges, head)
        if k is not None:
            cells.setdefault(k, {"heads": [], "values": [], "dims": []})["heads"].append(head)
    return cells


def _fill_cells(cells: dict[int, dict], layout: _Layout, edges: list[float]) -> None:
    for ln in layout.lines:
        if ln["bbox"][0] <= layout.label_right or not _is_horizontal(ln):
            continue
        k = _cell_of(edges, ln)
        if k in cells:
            _fill_cell(cells[k], ln, layout)


def _schedule_cells(page) -> tuple[_Layout, list[dict]] | None:
    layout = _layout(page)
    if layout is None:
        return None
    edges = _column_rules(page, layout)
    heads = _headers(layout)
    if not heads:
        return None
    if len(edges) < 2:
        edges = [s - 40 for s in sorted({round(h["bbox"][0]) for h in heads})] + [page.width * 2]
    cells = _header_cells(heads, edges)
    _fill_cells(cells, layout, edges)
    return layout, [cells[k] for k in sorted(cells)]


def _cell_locations(cell: dict, labels, preferred) -> dict[str, bool]:
    locations: dict[str, bool] = {}
    for head in cell["heads"]:
        for match in RE_GRID_REF.finditer(norm_text(head["text"])):
            loc = normalize_location(match.group(1), match.group(2), labels, preferred)
            if loc and loc not in locations:
                locations[loc] = location_fixed(match.group(1), match.group(2), loc)
    return locations


def _cell_bars(cell: dict, ties_y: float) -> tuple[list, list[str], int]:
    area = next((section_area(ln["text"]) for ln in cell["dims"] if section_area(ln["text"])), None)
    bars, texts, unread = [], [], 0
    for ln in sorted(cell["values"], key=lambda ln: ln["bbox"][1]):
        text = norm_text(ln["text"])
        role = "LIG" if RE_SHOP_SPACING.search(text) or ln["bbox"][1] >= ties_y - 10 else "VERT"
        bars.extend(shop_bars(text, role, role == "VERT", area))
        unread += unread_segments(text, role) if role == "VERT" else 0
        texts.append(f"{role}: {text}")
    return bars, texts, unread


def schedule_items(ctx: Ctx, page, labels, level: str, preferred=None) -> list:
    parsed = _schedule_cells(page)
    if parsed is None:
        return []
    layout, cells = parsed
    items = []
    for cell in cells:
        locations = _cell_locations(cell, labels, preferred)
        bars, texts, unread = _cell_bars(cell, layout.y("ETRIER"))
        armature = [a for a, _ in bars]
        if not locations or not armature:
            continue
        box = layout.frame.unbox(lines_bbox(cell["heads"] + cell["values"]))
        raw = " ".join(norm_text(h["text"]) for h in cell["heads"]) + ": " + " / ".join(texts)
        for loc, fixed in locations.items():
            confidence = reading_confidence(bars, fixed, unread)
            items.append(
                ocr_item(ctx, page, loc, level, box, [a.model_copy() for a in armature], raw, confidence)
            )
    return items
