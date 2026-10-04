from __future__ import annotations

import re
from functools import lru_cache

from ..geometry import center
from ..leaders import page_drawings, page_geometry
from ..rebar import norm_text
from .base import Ctx, make_item

TYPE = "fondation"

RE_LOC = re.compile(r"(?<![A-Z0-9.])([A-Z]{1,2}(?:\.\d)?)-(\d{1,2}(?:\.\d)?)(?![\d.])")
RE_TYPE_ROW = re.compile(r"^(?:TYPE\s*)?([A-Z0-9]{1,3})$")
RE_SHOP_TYPE = re.compile(r"TYPE[- ]?([A-Z0-9]{1,3})")
MAX_LETTER_DIST = 220.0
NEAREST_COLUMN_REACH = 35.0
MAX_FOOTING_SIDE = 450.0
MIN_FOOTING_SIDE = 20.0
GRID_MARGIN = 60.0
OUTLINE_LIMITS = (40.0, 40.0, MAX_FOOTING_SIDE)


def _edge_beyond(
    p0: float, p1: float, q0: float, q1: float, center_p: float, center_q: float
) -> tuple | None:
    reach, min_len, max_len = OUTLINE_LIMITS
    if abs(p0 - p1) >= 0.5 or not min_len <= abs(q1 - q0) <= max_len:
        return None
    if center_p < p0 < center_p + reach and min(q0, q1) <= center_q <= max(q0, q1):
        return (p0, min(q0, q1), max(q0, q1))
    return None


def _closer(edge: tuple | None, best: tuple | None) -> tuple | None:
    return edge if edge is not None and (best is None or edge[0] < best[0]) else best


def _footing_rect(geom, cx: float, cy: float):
    right = bottom = None
    for x0, y0, x1, y1 in geom.segs:
        right = _closer(_edge_beyond(x0, x1, y0, y1, cx, cy), right)
        bottom = _closer(_edge_beyond(y0, y1, x0, x1, cy, cx), bottom)
    if right is None or bottom is None:
        return None
    return (bottom[1], right[1], right[0], bottom[0])


def _light_fill(drawing: dict) -> bool:
    fill = drawing.get("fill")
    return drawing["type"] in ("f", "fs") and fill is not None and all(0.85 <= c <= 0.995 for c in fill)


@lru_cache(maxsize=32)
def _footing_areas(path: str, page_no: int) -> tuple:
    out = []
    for drawing in page_drawings(path, page_no):
        if not _light_fill(drawing):
            continue
        x0, y0, x1, y1 = drawing["rect"]
        if min(x1 - x0, y1 - y0) >= MIN_FOOTING_SIDE and max(x1 - x0, y1 - y0) <= MAX_FOOTING_SIDE:
            out.append((x0, y0, x1, y1))
    return tuple(out)


def _area_around(areas, cx: float, cy: float):
    inside = [a for a in areas if a[0] <= cx <= a[2] and a[1] <= cy <= a[3]]
    return min(inside, key=lambda a: (a[2] - a[0]) * (a[3] - a[1])) if inside else None


def _columns_in(geom, rect) -> list:
    if rect is None:
        return []
    return [
        s
        for s in geom.square_solids
        if rect[0] <= center(s)[0] <= rect[2] and rect[1] <= center(s)[1] <= rect[3]
    ]


def _nearest_column(geom, cx: float, cy: float):
    best = None
    for solid in geom.solids:
        px, py = center(solid)
        d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
        if d <= NEAREST_COLUMN_REACH and (best is None or d < best[0]):
            best = (d, (px, py))
    return best[1] if best else None


def _type_rows(ctx: Ctx, page) -> dict:
    rows = {}
    for block in ctx.blocks.get(page.key, []):
        if block.kind != "table_row" or "LONG" not in norm_text(block.meta["header"]):
            continue
        match = RE_TYPE_ROW.match(norm_text(block.meta["cells"][0]))
        if match:
            rows[match.group(1)] = block
    return rows


def _located(grid, points, confidence: float, how: str) -> list[tuple]:
    found = []
    for x, y in points:
        loc, d = grid.locate_precise(x, y)
        if loc:
            found.append((loc, d, confidence, how))
    return found


def _fallback_locations(geom, grid, rect, cx: float, cy: float) -> list[tuple]:
    if rect is not None:
        found = _located(grid, [center(rect)], 0.6, "outline")
        if found:
            return found
    near = _nearest_column(geom, cx, cy)
    found = _located(grid, [near], 0.7, "nearest column") if near is not None else []
    if found:
        return found
    hit = grid.nearest_in_quadrant(cx, cy, sx=-1, sy=-1, max_d=MAX_LETTER_DIST)
    return [(hit[0], hit[1], 0.5, "quadrant")] if hit is not None else []


def _tag_locations(geom, areas, grid, cx: float, cy: float) -> list[tuple]:
    in_area = _columns_in(geom, _area_around(areas, cx, cy))
    found = _located(grid, map(center, in_area), 0.95, "footing area")
    if found:
        return found
    rect = _footing_rect(geom, cx, cy)
    found = _located(grid, map(center, _columns_in(geom, rect)), 0.9, "outline")
    return found or _fallback_locations(geom, grid, rect, cx, cy)


def _grid_bounds(grid) -> tuple[float, float, float, float]:
    xs, ys = [g.pos for g in grid.verticals], [g.pos for g in grid.horizontals]
    return min(xs) - GRID_MARGIN, max(xs) + GRID_MARGIN, min(ys) - GRID_MARGIN, max(ys) + GRID_MARGIN


def _is_tag_position(cx: float, cy: float, grid, bounds, table_boxes) -> bool:
    x_lo, x_hi, y_lo, y_hi = bounds
    if not (x_lo < cx < x_hi and y_lo < cy < y_hi):
        return False
    if any(b[0] - 5 <= cx <= b[2] + 5 and b[1] - 5 <= cy <= b[3] + 5 for b in table_boxes):
        return False
    on_grid_line = any(abs(g.pos - cy) < 3 for g in grid.horizontals)
    return not (on_grid_line and (cx < x_lo + 80 or cx > x_hi - 80))


def _type_tags(ctx: Ctx, page, rows: dict, grid) -> list[tuple]:
    table_boxes = [b.bbox for b in ctx.blocks.get(page.key, []) if b.kind == "table_row"]
    bounds = _grid_bounds(grid)
    tags = []
    for ln in page.lines:
        text = norm_text(ln["text"])
        if text in rows and _is_tag_position(*center(ln["bbox"]), grid, bounds, table_boxes):
            tags.append((text, ln, *center(ln["bbox"])))
    return tags


def _best_tags(page, grid, tags: list[tuple]) -> dict[str, tuple]:
    geom = page_geometry(str(page.path), page.page)
    areas = _footing_areas(str(page.path), page.page)
    best: dict[str, tuple] = {}
    for text, ln, cx, cy in tags:
        for loc, d, confidence, how in _tag_locations(geom, areas, grid, cx, cy):
            if loc not in best or d < best[loc][1]:
                best[loc] = (text, d, ln, confidence, how)
    return best


def _plan_item(ctx: Ctx, page, row, loc: str, tag: tuple):
    text, d, ln, confidence, how = tag
    read = ctx.read(row)
    return make_item(
        ctx,
        page,
        id=f"{page.feuillet}_{loc}_plan",
        type_element=TYPE,
        bbox=ln["bbox"],
        read=read,
        element=f"TYPE {text}",
        niveau="FONDATION",
        localisation=loc,
        texte_brut=f"TYPE {text} -> " + " | ".join(row.meta["cells"]),
        confiance=round(min(read.get("confiance", 0.5), confidence), 2),
        localisation_note=f"{how}: tag {text}, column {d:.0f}pt from {loc}",
    )


def _plan_items(ctx: Ctx):
    items = []
    for page in ctx.pages_of("plan", TYPE):
        grid = ctx.grids.get(page.key)
        rows = _type_rows(ctx, page)
        if not rows or grid is None or not grid.ok:
            continue
        best = _best_tags(page, grid, _type_tags(ctx, page, rows, grid))
        items += [_plan_item(ctx, page, rows[tag[0]], loc, tag) for loc, tag in best.items()]
    return items


def _has_footing_bars(read: dict) -> bool:
    return any(a.role in ("LONG", "TRAN") for a in read["armature"])


def _footing_element(texts: list[str]) -> tuple[bool, str | None]:
    footing_type = next((RE_SHOP_TYPE.search(t) for t in texts if "TYPE" in t), None)
    return footing_type is not None, f"TYPE {footing_type.group(1)}" if footing_type else None


def _shop_block_items(ctx: Ctx, page, block) -> list:
    texts = [norm_text(t) for t in block.texts]
    column_line = next((t for t in texts if t.startswith("COLONNE")), None)
    if not column_line:
        return []
    typed, element = _footing_element(texts)
    read = ctx.read(block)
    if not typed and not _has_footing_bars(read):
        return []
    locations = [f"{m.group(1)}-{m.group(2)}" for m in RE_LOC.finditer(column_line)]
    return [
        make_item(
            ctx,
            page,
            id=f"{page.key}_{loc}",
            type_element=TYPE,
            block=block,
            read=read,
            element=element,
            niveau="FONDATION",
            localisation=loc,
        )
        for loc in locations
    ]


def _shop_items(ctx: Ctx):
    return [
        item
        for page in ctx.pages_of("atelier", TYPE)
        for block in ctx.blocks.get(page.key, [])
        if block.kind == "stack"
        for item in _shop_block_items(ctx, page, block)
    ]


def extract(ctx: Ctx):
    return _plan_items(ctx), _shop_items(ctx)
