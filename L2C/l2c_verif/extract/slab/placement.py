from __future__ import annotations

import re
from functools import lru_cache
from itertools import pairwise
from statistics import median

from ...grid import label_value
from ...ingest import normalize_level
from ...leaders import page_drawings
from ...rebar import norm_text
from ..base import Ctx

TYPE = "dalle"
COL_SNAP = 0.12
PERP_TOL = 0.42
ALONG_TOL = 0.75
PERP_WEIGHT = 1.5
DEFAULT_SCALE = 150.0
MIN_COLUMNS = 4
RE_PLAN_TITLE = re.compile(r"\bPLAN\b")


def _plan_level(page) -> str | None:
    titles = [
        norm_text(ln["text"])
        for ln in page.lines
        if ln["size"] >= 14 and RE_PLAN_TITLE.search(norm_text(ln["text"]))
    ]
    for text in [*titles, norm_text(page.titre or "")]:
        if "TREFOND" in text:
            return "TREFOND"
        level = normalize_level(text)
        if level:
            return level
    return page.niveau


def _scale(grid) -> float:
    gaps = [b.pos - a.pos for lines in (grid.horizontals, grid.verticals) for a, b in pairwise(lines)]
    gaps = [g for g in gaps if g > 1]
    return max(median(gaps) * 1.6, 40.0) if gaps else DEFAULT_SCALE


@lru_cache(maxsize=128)
def _filled_rects(path: str, page_no: int) -> tuple:
    out = []
    for drawing in page_drawings(path, page_no):
        fill = drawing.get("fill")
        if drawing["type"] not in ("f", "fs") or fill is None or min(fill) > 0.95:
            continue
        x0, y0, x1, y1 = drawing["rect"]
        if 4 <= x1 - x0 <= 60 and 4 <= y1 - y0 <= 60:
            out.append(((x0 + x1) / 2, (y0 + y1) / 2))
    return tuple(out)


def _columns(page, grid, scale: float) -> list[tuple[str, float, float]]:
    snap = COL_SNAP * scale
    points = _filled_rects(str(page.path), page.page)
    columns = [
        (label, ix, iy)
        for label, ix, iy in grid.intersections()
        if any(abs(px - ix) <= snap and abs(py - iy) <= snap for px, py in points)
    ]
    return columns if len(columns) >= MIN_COLUMNS else list(grid.intersections())


def anchor(annotation: dict) -> tuple[float, float]:
    x0, y0, x1, y1 = annotation.get("abox") or annotation["bbox"]
    return (x0, (y0 + y1) / 2) if annotation["axis"] == "H" else ((x0 + x1) / 2, y1)


def _assign(annotation: dict, columns, scale: float, along_tol: float | None = ALONG_TOL):
    ax, ay = anchor(annotation)
    hits = []
    for label, ix, iy in columns:
        perp, along = (ay - iy, ax - ix) if annotation["axis"] == "H" else (ax - ix, ay - iy)
        if abs(perp) > PERP_TOL * scale or (along_tol is not None and abs(along) > along_tol * scale):
            continue
        hits.append((abs(along) + PERP_WEIGHT * abs(perp), label, perp))
    if not hits:
        return None
    hits.sort()
    score, label, perp = hits[0]
    second = next((h[0] for h in hits[1:] if h[1] != label), None)
    return label, perp, score, second


def _grid_coordinate(lines, pos: float) -> float:
    points = sorted((g.pos, label_value(g.label)) for g in lines)
    if len(points) < 2:
        return 0.0
    (p0, v0), (p1, v1) = next(pair for pair in pairwise(points) if pos <= pair[1][0] or pair[1] == points[-1])
    return v0 + (v1 - v0) * (pos - p0) / ((p1 - p0) or 1.0)


def _place(annotation: dict, grid, columns: list, scale: float) -> tuple | None:
    hit = _assign(annotation, columns, scale)
    if hit is None:
        hit = _assign(annotation, list(grid.intersections()), scale, along_tol=None)
        if hit is None:
            return None
        annotation["amb"].append("no column symbol at the nearest intersection")
    if hit[3] is not None and hit[3] < 1.3 * hit[2] + 0.05 * scale:
        annotation["amb"].append("text between two columns")
    return hit


def _page_level(page, source: str) -> str | None:
    return _plan_level(page) if source == "plan" else page.niveau


def collect(ctx: Ctx, source: str, parse) -> list[dict]:
    placed = []
    for page in ctx.pages_of(source, TYPE):
        grid = ctx.grids.get(page.key)
        found = parse(page) if grid is not None and grid.ok else []
        level = _page_level(page, source) if found else None
        if not level:
            continue
        scale = _scale(grid)
        columns = _columns(page, grid, scale)
        for annotation in found:
            hit = _place(annotation, grid, columns, scale)
            if hit is None:
                continue
            ax, ay = anchor(annotation)
            u = (_grid_coordinate(grid.verticals, ax), _grid_coordinate(grid.horizontals, ay))
            annotation.update(page=page, level=level, loc=hit[0], perp=hit[1], score=hit[2] / scale, u=u)
            placed.append(annotation)
    return placed
