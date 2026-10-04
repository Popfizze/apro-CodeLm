from __future__ import annotations

from functools import lru_cache

import fitz

from ...geometry import connected_groups
from ...leaders import rotated_drawings

TOUCH_TOL = 1.5
MAX_TITLE_GAP = 400.0


def _is_pink(c) -> bool:
    return c is not None and c[0] > 0.95 and 0.7 < c[1] < 0.86 and abs(c[1] - c[2]) < 0.03


def _is_grey(c) -> bool:
    return c is not None and abs(c[0] - c[1]) < 0.02 and abs(c[1] - c[2]) < 0.02 and 0.25 <= c[0] <= 0.985


def _dark_stroke(drawing: dict) -> bool:
    color = drawing.get("color")
    return drawing.get("type") in ("s", "fs") and color is not None and max(color) < 0.35


def _line_segments(drawing: dict) -> list[tuple]:
    segments = []
    for item in drawing["items"]:
        if item[0] == "l":
            p, q = item[1], item[2]
            segments.append((min(p.x, q.x), min(p.y, q.y), max(p.x, q.x), max(p.y, q.y)))
    return segments


@lru_cache(maxsize=16)
def wall_fills(path: str, page_no: int):
    pink, grey, segs = [], [], []
    with fitz.open(path) as doc:
        drawings = rotated_drawings(doc[page_no - 1])
    for drawing in drawings:
        if _dark_stroke(drawing):
            segs.extend(_line_segments(drawing))
        r = drawing["rect"]
        if drawing.get("type") not in ("f", "fs") or r.width < 4 or r.height < 4:
            continue
        if _is_pink(drawing.get("fill")):
            pink.append((r.x0, r.y0, r.x1, r.y1))
        elif _is_grey(drawing.get("fill")):
            grey.append((r.x0, r.y0, r.x1, r.y1))
    return pink, grey, segs


def _far_end(segment: tuple, x0: float, x1: float, cy: float) -> float | None:
    sx0, sy0, sx1, sy1 = segment
    if sy1 - sy0 > 1.0 or sx1 - sx0 < 15 or abs(sy0 - cy) > 3.5:
        return None
    if x1 - 3 <= sx0 <= x1 + 12:
        return sx1
    if x0 - 12 <= sx1 <= x0 + 3:
        return sx0
    return None


def leader_end(segs: list[tuple], x0: float, x1: float, cy: float) -> float | None:
    middle = (x0 + x1) / 2
    best = None
    for segment in segs:
        far = _far_end(segment, x0, x1, cy)
        if far is not None and (best is None or abs(far - middle) > abs(best - middle)):
            best = far
    return best


def _touch(a, b) -> bool:
    t = TOUCH_TOL
    return a[0] <= b[2] + t and b[0] <= a[2] + t and a[1] <= b[3] + t and b[1] <= a[3] + t


def _touching_pairs(rects: list[tuple]):
    order = sorted(range(len(rects)), key=lambda i: rects[i][0])
    for k, i in enumerate(order):
        for j in order[k + 1 :]:
            if rects[j][0] > rects[i][2] + TOUCH_TOL:
                break
            if _touch(rects[i], rects[j]):
                yield i, j


def _nearest_title(titles: list[tuple], x0: float, x1: float, y0: float) -> str | None:
    best = None
    for letter, tx, ty in titles:
        if ty < y0:
            continue
        gap = max(x0 - tx, tx - x1, 0.0)
        if best is None or gap < best[1]:
            best = (letter, gap)
    return best[0] if best and best[1] <= MAX_TITLE_GAP else None


def elevation_letters(pink: list[tuple], grey: list[tuple], titles: list[tuple]) -> dict[int, str | None]:
    rects = pink + grey
    letters: dict[int, str | None] = {}
    for component in connected_groups(len(rects), _touching_pairs(rects)):
        pink_members = [i for i in component if i < len(pink)]
        if not pink_members:
            continue
        x0 = min(rects[i][0] for i in component)
        x1 = max(rects[i][2] for i in component)
        y0 = min(rects[i][1] for i in component)
        letter = _nearest_title(titles, x0, x1, y0)
        letters.update(dict.fromkeys(pink_members, letter))
    return letters
