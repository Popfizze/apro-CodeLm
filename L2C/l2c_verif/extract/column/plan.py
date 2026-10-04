from __future__ import annotations

import re

from ...blocks import Block
from ...geometry import center
from ...leaders import page_geometry
from ...rebar import has_rebar, norm_text
from ..base import Ctx, make_item
from .items import TYPE
from .labels import PrimedGrid, primed_verticals, usable_grid

ANCHOR_DX = 20.0
MAX_ASSOC = 90.0
CLOSE_DISTANCE = 40.0
RE_SIZE_HEAD = re.compile(r"^COL\.?\s*\d")
UNSPECIFIED_NOTE = "armature non indiquée au plan"


def _corner_anchors(bbox) -> list[tuple[tuple[float, float], float]]:
    x0, y0, x1, y1 = bbox
    return [
        ((x1 + ANCHOR_DX, y0), 0.0),
        ((x0 - ANCHOR_DX, y0), 15.0),
        ((x1 + ANCHOR_DX, y1), 25.0),
        ((x0 - ANCHOR_DX, y1), 25.0),
    ]


def _associate(grid, bbox):
    best = None
    for (ax, ay), penalty in _corner_anchors(bbox):
        loc, d = grid.locate(ax, ay)
        if loc is not None and (best is None or d + penalty < best[1] + best[2]):
            best = (loc, d, penalty)
    return best


def _via_leader(geom, grid, bbox):
    box = geom.box_around(bbox)
    end = geom.follow_leader(box) if box is not None else None
    if end is None:
        return None
    solid = geom.solid_at(*end)
    loc, d = grid.locate_precise(*center(solid)) if solid else grid.locate(*end)
    if loc is None:
        return None
    return loc, d, solid is not None


def _leader_confidence(d: float, on_solid: bool) -> float:
    if d > CLOSE_DISTANCE:
        return 0.45
    return 0.95 if on_solid else 0.7


def _locate(geom, grid, bbox):
    lead = _via_leader(geom, grid, bbox)
    if lead is not None and lead[1] <= MAX_ASSOC:
        loc, d, on_solid = lead
        return loc, d, _leader_confidence(d, on_solid), "leader"
    hit = _associate(grid, bbox)
    if hit is None:
        return None
    loc, d, penalty = hit
    return loc, d, 0.6 if d <= CLOSE_DISTANCE and penalty == 0 else 0.4, "corner"


def _stack_below(page, ln: dict) -> list[dict]:
    height = max(ln["bbox"][3] - ln["bbox"][1], 1.0)
    below = [
        o
        for o in page.lines
        if o is not ln
        and abs(o["bbox"][0] - ln["bbox"][0]) <= 3
        and 0 <= o["bbox"][1] - ln["bbox"][3] <= 4 * height
    ]
    return [ln, *below]


def _callouts_without_rebar(ctx: Ctx, page) -> list[Block]:
    in_blocks = {id(ln) for b in ctx.blocks.get(page.key, []) for ln in b.lines}
    out = []
    for ln in page.lines:
        if id(ln) in in_blocks or not RE_SIZE_HEAD.match(norm_text(ln["text"])):
            continue
        group = _stack_below(page, ln)
        if any(has_rebar(o["text"]) for o in group):
            continue
        if any(norm_text(o["text"]).startswith("BETON") for o in group):
            out.append(Block(f"{page.key}_c{len(out)}", page, sorted(group, key=lambda o: o["bbox"][1])))
    return out


def _callout_item(ctx: Ctx, page, block: Block, found: tuple, n: int):
    loc, d, location_confidence, how = found
    read = ctx.read(block)
    size = next((t for t in (norm_text(t) for t in block.texts) if t.startswith("COL")), None)
    note = f"{how}: {d:.0f}pt from {loc}" + ("" if read.get("armature") else f"; {UNSPECIFIED_NOTE}")
    confidence = round(min(read.get("confiance", 0.5), location_confidence), 2)
    return make_item(
        ctx,
        page,
        id=f"{page.feuillet}_{loc}_plan" + (f"_{n + 1}" if n else ""),
        type_element=TYPE,
        block=block,
        read=read,
        element=size.replace("COL.", "COL").strip() if size else loc,
        niveau=page.niveau,
        localisation=loc,
        confiance=confidence if read.get("armature") else location_confidence,
        localisation_note=note,
    )


def _page_items(ctx: Ctx, page, grid) -> list:
    primes = primed_verticals(page, grid)
    if primes:
        grid = PrimedGrid(grid, primes)
    geom = page_geometry(str(page.path), page.page)
    callouts = [
        b for b in ctx.blocks.get(page.key, []) if any(norm_text(t).startswith("ARM") for t in b.texts)
    ]
    items, seen = [], {}
    for block in callouts + _callouts_without_rebar(ctx, page):
        found = _locate(geom, grid, block.bbox)
        if found is None:
            continue
        n = seen.get(found[0], 0)
        seen[found[0]] = n + 1
        items.append(_callout_item(ctx, page, block, found, n))
    return items


def plan_items(ctx: Ctx) -> list:
    items = []
    for page in ctx.pages_of("plan", TYPE):
        grid = usable_grid(ctx, page)
        if grid is not None and grid.ok:
            items += _page_items(ctx, page, grid)
    return items
