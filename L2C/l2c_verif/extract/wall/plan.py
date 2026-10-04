from __future__ import annotations

import re
from dataclasses import dataclass

from ...geometry import center, lines_bbox
from ...ingest import PageRef
from ...rebar import norm_text, parse_line
from ..base import Ctx, make_item
from ..frame import Frame
from .drawing import elevation_letters, leader_end, wall_fills
from .levels import band, elevation_levels, elevation_titles, grid_bubbles

TYPE = "mur"

RE_ARM = re.compile(r"^ARM\.?\s*:?\s*\d+\s*-\s*\d{2}M")
RE_LEGEND = re.compile(r"CONCENTRATION D'ARMATURE \(VOIR ELEVATION\)")
MAX_CALLOUT_GAP = 260.0
NOTES_ZONE = 0.82
MIN_CONCENTRATION_HEIGHT = 25.0


@dataclass
class _Sheet:
    page: PageRef
    frame: Frame
    lines: list[dict]
    x_max: float
    pink: list[tuple]
    segs: list[tuple]
    levels: list[tuple]
    letters: dict[int, str | None]
    bubbles: list[tuple]


@dataclass
class _Link:
    index: int
    gap: float
    by_leader: bool


def _is_wall_page(page: PageRef) -> bool:
    if page.source != "plan":
        return False
    if page.type_element == TYPE:
        return True
    return page.type_element is None and any(RE_LEGEND.search(norm_text(ln["text"])) for ln in page.lines)


def _sheet(page: PageRef) -> _Sheet | None:
    frame = Frame(page)
    lines = frame.lines(page.lines)
    x_max = frame.width * NOTES_ZONE
    pink_all, grey_all, segs = wall_fills(str(page.path), page.page)
    pink = [b for b in map(frame.box, pink_all) if b[0] <= x_max and b[3] - b[1] >= MIN_CONCENTRATION_HEIGHT]
    if not pink:
        return None
    grey = [b for b in map(frame.box, grey_all) if b[0] <= x_max]
    letters = elevation_letters(pink, grey, elevation_titles(lines))
    return _Sheet(
        page,
        frame,
        lines,
        x_max,
        pink,
        [frame.box(s) for s in segs],
        elevation_levels(lines),
        letters,
        grid_bubbles(lines),
    )


def _vertical_gap(callout: dict, ln: dict, above: bool) -> float | None:
    ax0, ay0, ax1, ay1 = callout["bbox"]
    x0, y0, x1, y1 = ln["bbox"]
    if x0 > ax1 + 5 or x1 < ax0 - 5:
        return None
    gap = (ay0 - y1) if above else (y0 - ay1)
    return gap if -3 <= gap <= 6 else None


def _near(lines: list[dict], callout: dict, prefixes: tuple[str, ...], above: bool) -> dict | None:
    best = None
    for ln in lines:
        if ln is callout or not norm_text(ln["text"]).startswith(prefixes):
            continue
        gap = _vertical_gap(callout, ln, above)
        if gap is not None and (best is None or gap < best[0]):
            best = (gap, ln)
    return best[1] if best else None


def _gap(rect: tuple, x0: float, x1: float) -> float:
    return max(rect[0] - x1, x0 - rect[2], 0.0)


def _by_leader(sheet: _Sheet, candidates: list, box: tuple) -> _Link | None:
    x0, y0, x1, y1 = box
    end = leader_end(sheet.segs, x0, x1, (y0 + y1) / 2)
    if end is None:
        return None
    hits = [(i, r) for i, r in candidates if r[0] - 4 <= end <= r[2] + 4]
    if not hits:
        return None
    i, rect = min(hits, key=lambda h: abs((h[1][0] + h[1][2]) / 2 - end))
    return _Link(i, _gap(rect, x0, x1), True)


def _by_distance(candidates: list, box: tuple) -> _Link | None:
    best = None
    for i, rect in candidates:
        gap = _gap(rect, box[0], box[2])
        if gap <= MAX_CALLOUT_GAP and (best is None or gap < best.gap):
            best = _Link(i, gap, False)
    return best


def _concentration(sheet: _Sheet, callout: dict) -> _Link | None:
    cy = (callout["bbox"][1] + callout["bbox"][3]) / 2
    candidates = [(i, r) for i, r in enumerate(sheet.pink) if r[1] - 12 <= cy <= r[3] + 12]
    return _by_leader(sheet, candidates, callout["bbox"]) or _by_distance(candidates, callout["bbox"])


def _axis(sheet: _Sheet, rect: tuple) -> str | None:
    rcx = center(rect)[0]
    above = [b for b in sheet.bubbles if b[1] < rect[1] and abs(b[0] - rcx) < 100]
    return min(above, key=lambda b: abs(b[0] - rcx))[2] if above else None


def _bars(callout: dict, ties: dict | None) -> list:
    bars = parse_line(callout["text"]) + (parse_line(ties["text"]) if ties else [])
    if "GOUJ" in norm_text(callout["text"]):
        for bar in bars:
            if bar.role == "VERT":
                bar.repere = "VERT+GOUJ"
    return bars


def _note(sheet: _Sheet, rect: tuple, link: _Link, axis: str | None) -> str:
    how = "leader" if link.by_leader else f"nearest, gap {link.gap:.0f}pt"
    grid = f", grid {axis}" if axis else ""
    return f"concentration {[round(v) for v in sheet.frame.unbox(rect)]}, {how}{grid}"


def _confidence(letter: str | None, upper: tuple | None, link: _Link) -> float:
    if letter and upper and (link.by_leader or link.gap <= 120):
        return 0.9
    return 0.6


def _element(dimensions: dict | None, axis: str | None) -> str:
    label = norm_text(dimensions["text"]).replace("CA.", "CA").strip() if dimensions else "CA"
    return f"{label} - AXE {axis}" if axis else label


def _numbered(key: str, seen: dict[str, int]) -> str:
    n = seen.get(key, 0)
    seen[key] = n + 1
    return key + (f"_{n + 1}" if n else "") + "_plan"


def _item(ctx: Ctx, sheet: _Sheet, callout: dict, link: _Link, seen: dict[str, int]):
    rect = sheet.pink[link.index]
    letter = sheet.letters.get(link.index)
    lower, upper = band(sheet.levels, rect[0], center(rect)[1])
    if lower is None:
        return None
    loc = f"ELEVATION {letter or '?'} - {lower[0]} @ {upper[0] if upper else '?'}"
    axis = _axis(sheet, rect)
    dimensions = _near(sheet.lines, callout, ("CA",), True)
    ties = _near(sheet.lines, callout, ("LIG", "ETR"), False)
    stack = [s for s in (dimensions, callout, ties) if s is not None]
    side = axis or ("G" if center(rect)[0] > callout["bbox"][2] else "D")
    confidence = _confidence(letter, upper, link)
    return make_item(
        ctx,
        sheet.page,
        id=_numbered(f"{sheet.page.feuillet}_{loc}_{side}", seen),
        type_element=TYPE,
        bbox=sheet.frame.unbox(lines_bbox(stack)),
        armature=_bars(callout, ties),
        read={"confiance": confidence, "methode": "regex"},
        element=_element(dimensions, axis),
        niveau=lower[1],
        localisation=loc,
        texte_brut=" / ".join(s["text"] for s in stack),
        confiance=confidence,
        localisation_note=_note(sheet, rect, link, axis),
    )


def _sheet_items(ctx: Ctx, sheet: _Sheet) -> list:
    items, seen = [], {}
    for ln in sheet.lines:
        if not RE_ARM.match(norm_text(ln["text"])) or ln["bbox"][0] > sheet.x_max:
            continue
        link = _concentration(sheet, ln)
        item = _item(ctx, sheet, ln, link, seen) if link is not None else None
        if item is not None:
            items.append(item)
    return items


def extract(ctx: Ctx):
    sheets = [_sheet(page) for page in ctx.pages if _is_wall_page(page)]
    return [item for sheet in sheets if sheet is not None for item in _sheet_items(ctx, sheet)], []
