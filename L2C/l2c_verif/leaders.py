from __future__ import annotations

from functools import lru_cache
from itertools import pairwise

import fitz

Box = tuple[float, float, float, float]
GRID_CELL = 6.0
BORDER_TOL = 1.5
OUTSIDE_MARGIN = 3.0


def _dark(color) -> bool:
    return color is not None and max(color) < 0.35


def _rotate_drawing(drawing: dict, matrix) -> dict:
    items = []
    for item in drawing["items"]:
        if item[0] == "l":
            items.append(("l", item[1] * matrix, item[2] * matrix))
        elif item[0] == "re":
            items.append(("qu", item[1].quad * matrix))
        elif item[0] == "qu":
            items.append(("qu", item[1] * matrix))
    return {**drawing, "rect": drawing["rect"] * matrix, "items": items}


def rotated_drawings(page: fitz.Page) -> list[dict]:
    drawings = page.get_drawings()
    if not page.rotation:
        return drawings
    return [_rotate_drawing(d, page.rotation_matrix) for d in drawings]


def _axis_aligned(item) -> bool:
    if item[0] in ("re", "qu"):
        return True
    if item[0] == "l":
        p, q = item[1], item[2]
        return abs(p.x - q.x) < 0.5 or abs(p.y - q.y) < 0.5
    return False


def _stroke_segments(drawing: dict):
    for item in drawing["items"]:
        if item[0] == "l":
            yield (item[1].x, item[1].y, item[2].x, item[2].y)
        elif item[0] in ("re", "qu"):
            quad = item[1].quad if item[0] == "re" else item[1]
            corners = [quad.ul, quad.ur, quad.lr, quad.ll, quad.ul]
            yield from ((a.x, a.y, b.x, b.y) for a, b in pairwise(corners))


def _on_border(x: float, y: float, box: Box) -> bool:
    x0, y0, x1, y1 = box
    on_side = (
        abs(x - x0) <= BORDER_TOL or abs(x - x1) <= BORDER_TOL
    ) and y0 - BORDER_TOL <= y <= y1 + BORDER_TOL
    on_edge = (
        abs(y - y0) <= BORDER_TOL or abs(y - y1) <= BORDER_TOL
    ) and x0 - BORDER_TOL <= x <= x1 + BORDER_TOL
    return on_side or on_edge


def _outside(x: float, y: float, box: Box) -> bool:
    x0, y0, x1, y1 = box
    m = OUTSIDE_MARGIN
    return x < x0 - m or x > x1 + m or y < y0 - m or y > y1 + m


def _segment_length(segment: Box) -> float:
    return abs(segment[0] - segment[2]) + abs(segment[1] - segment[3])


class PageGeometry:
    def __init__(self, page: fitz.Page):
        self.segs: list[Box] = []
        self.solids: list[Box] = []
        self.square_solids: list[Box] = []
        for drawing in rotated_drawings(page):
            self._add_solid(drawing)
            if drawing["type"] in ("s", "fs") and _dark(drawing.get("color")):
                self.segs.extend(_stroke_segments(drawing))
        self.cell = GRID_CELL
        self.idx: dict[tuple[int, int], list[int]] = {}
        for i, (x0, y0, x1, y1) in enumerate(self.segs):
            for x, y in ((x0, y0), (x1, y1)):
                self.idx.setdefault((int(x // self.cell), int(y // self.cell)), []).append(i)

    def _add_solid(self, drawing: dict) -> None:
        if drawing["type"] not in ("f", "fs") or not _dark(drawing.get("fill")):
            return
        r = drawing["rect"]
        if 4 <= r.width <= 80 and 4 <= r.height <= 80:
            self.solids.append((r.x0, r.y0, r.x1, r.y1))
            if all(_axis_aligned(item) for item in drawing["items"]):
                self.square_solids.append((r.x0, r.y0, r.x1, r.y1))

    def near_endpoints(self, x: float, y: float, tol: float = 1.5):
        cx, cy = int(x // self.cell), int(y // self.cell)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for i in self.idx.get((gx, gy), []):
                    x0, y0, x1, y1 = self.segs[i]
                    if abs(x0 - x) <= tol and abs(y0 - y) <= tol:
                        yield i, (x1, y1)
                    elif abs(x1 - x) <= tol and abs(y1 - y) <= tol:
                        yield i, (x0, y0)

    def segments_in(self, rect: Box):
        x0, y0, x1, y1 = rect
        for s in self.segs:
            if (
                min(s[0], s[2]) >= x0
                and max(s[0], s[2]) <= x1
                and min(s[1], s[3]) >= y0
                and max(s[1], s[3]) <= y1
            ):
                yield s

    def box_around(self, text_box: Box, pad: float = 25.0) -> Box | None:
        tx0, ty0, tx1, ty1 = text_box
        tops, bottoms = [], []
        for x0, y0, x1, y1 in self.segments_in((tx0 - pad, ty0 - 8, tx1 + pad, ty1 + 8)):
            lo, hi = min(x0, x1), max(x0, x1)
            if abs(y0 - y1) > 0.5 or lo > tx0 + 2 or hi < tx1 - 25:
                continue
            if y0 <= ty0 + 2:
                tops.append((y0, lo, hi))
            elif y0 >= ty1 - 2:
                bottoms.append((y0, lo, hi))
        if not tops or not bottoms:
            return None
        top, bottom = max(tops), min(bottoms)
        return (min(top[1], bottom[1]), top[0], max(top[2], bottom[2]), bottom[0])

    def _leader_starts(self, box: Box) -> list[tuple[int, tuple[float, float]]]:
        starts = []
        for i, (x0, y0, x1, y1) in enumerate(self.segs):
            for (ax, ay), (ox, oy) in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
                if _on_border(ax, ay, box) and _outside(ox, oy, box):
                    starts.append((i, (ox, oy)))
                    break
        return starts

    def follow_leader(self, box: Box, max_hops: int = 8) -> tuple[float, float] | None:
        starts = self._leader_starts(box)
        if not starts:
            return None
        i, end = max(starts, key=lambda start: _segment_length(self.segs[start[0]]))
        used = {i}
        for _ in range(max_hops):
            step = next(((j, other) for j, other in self.near_endpoints(*end) if j not in used), None)
            if step is None:
                break
            used.add(step[0])
            end = step[1]
        return end

    def solid_at(self, x: float, y: float, tol: float = 4.0):
        for r in self.solids:
            if r[0] - tol <= x <= r[2] + tol and r[1] - tol <= y <= r[3] + tol:
                return r
        return None


@lru_cache(maxsize=16)
def page_drawings(path: str, page_no: int) -> tuple:
    with fitz.open(path) as doc:
        return tuple(doc[page_no - 1].get_cdrawings())


@lru_cache(maxsize=64)
def page_geometry(path: str, page_no: int) -> PageGeometry:
    with fitz.open(path) as doc:
        return PageGeometry(doc[page_no - 1])
