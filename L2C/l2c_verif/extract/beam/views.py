from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

from ...geometry import center
from ...models import Armature
from ...rebar import norm_text
from ..base import Ctx
from .reread import reread_lines
from .text import fix_ocr, parse_line, titles

TYPE = "poutre"
RE_FACE = re.compile(r"^(CH\.?\s*FACE|C\.F\.)")
VIEW_HEIGHT_RATIO = 0.22


@dataclass
class Bar:
    zone: str
    arm: Armature
    u: float
    y: float
    h: float
    text: str
    bbox: tuple
    explicit: bool = False


@dataclass
class View:
    beam: str
    title: str
    page: object
    bbox: tuple
    region: tuple
    bars: list[Bar] = field(default_factory=list)
    ocr: bool = False
    row: int = 0
    row_bars: list[Bar] = field(default_factory=list)


def split_y(bars: list[Bar]) -> float | None:
    ys = sorted((b.y, b.h) for b in bars)
    if len(ys) < 2:
        return None
    gap, i = max((ys[i + 1][0] - ys[i][0], i) for i in range(len(ys) - 1))
    return (ys[i][0] + ys[i + 1][0]) / 2 if gap > 1.2 * median(b.h for b in bars) else None


def _overlaps(a: tuple, b: tuple) -> bool:
    ax, ay = center(a[2])
    return b[2][0] <= ax <= b[2][2] and b[2][1] - 2 <= ay <= b[2][3] + 2


def _overlap_either(a: tuple, b: tuple) -> bool:
    return _overlaps(a, b) or _overlaps(b, a)


def _renamed(title: tuple, known: list[tuple], known_ids: frozenset) -> tuple:
    if title[0] in known_ids:
        return title
    alternative = next((a for a in known if _overlap_either(a, title)), None)
    return title if alternative is None else (alternative[0], *title[1:])


def _reconcile_titles(found: list[tuple], alternatives: list[tuple], known_ids: frozenset) -> list[tuple]:
    known = [a for a in alternatives if a[0] in known_ids]
    out = [_renamed(title, known, known_ids) for title in found]
    for alternative in known:
        if not any(_overlap_either(alternative, t) for t in out):
            out.append(alternative)
    return out


def _title_rows(found: list[tuple]) -> list[list[tuple]]:
    rows: list[list[tuple]] = []
    for title in found:
        y, h = center(title[2])[1], title[2][3] - title[2][1]
        row = next((r for r in rows if abs(median(center(o[2])[1] for o in r) - y) < 3 * h), None)
        if row is None:
            rows.append([title])
        else:
            row.append(title)
    return rows


def _half_widths(xs: list[float], k: int, width: float) -> tuple[float, float]:
    left = (xs[k] - xs[k - 1]) / 2 if k > 0 else None
    right = (xs[k + 1] - xs[k]) / 2 if k + 1 < len(xs) else None
    if left is None:
        left = 1.3 * right if right is not None else 2.0 * width
    if right is None:
        right = 1.3 * (xs[k] - xs[k - 1]) / 2 if k > 0 else 2.0 * width
    return left, right


def _view_top(found: list[tuple], title: tuple, x0: float, x1: float, max_height: float) -> float:
    box = title[2]
    y, h = center(box)[1], box[3] - box[1]
    above = [
        o[2][3]
        for o in found
        if o[2][3] < box[1] - 10 and o[2][2] > x0 and o[2][0] < x1 and abs(center(o[2])[1] - y) >= 3 * h
    ]
    return max([box[1] - max_height] + [a + 2 for a in above])


def page_views(
    page, lines: list[dict], ocr: bool, known_ids: frozenset = frozenset(), alternative_lines=None
):
    found = titles(lines)
    if known_ids and alternative_lines is not None:
        found = _reconcile_titles(found, titles(alternative_lines), known_ids)
    found.sort(key=lambda t: (center(t[2])[1], t[2][0]))
    views: list[View] = []
    for index, row in enumerate(_title_rows(found)):
        row.sort(key=lambda t: t[2][0])
        xs = [center(t[2])[0] for t in row]
        for k, title in enumerate(row):
            left, right = _half_widths(xs, k, title[2][2] - title[2][0])
            x0, x1 = xs[k] - left, xs[k] + right
            top = _view_top(found, title, x0, x1, VIEW_HEIGHT_RATIO * page.height)
            region = (x0, top, x1, title[2][1] + 2)
            views.append(View(title[0], title[1], page, title[2], region, ocr=ocr, row=index))
    return views


def _skin_context(ln: dict, skin_lines: list[dict], face_lines: list[dict]) -> bool:
    b, xc = ln["bbox"], center(ln["bbox"])[0]
    near_skin = any(
        abs(p["bbox"][0] - b[0]) < 20 and 0 < b[1] - p["bbox"][1] < 3 * ln["size"] for p in skin_lines
    )
    return near_skin or any(
        abs(center(p["bbox"])[0] - xc) < 40 and 0 < p["bbox"][1] - b[1] < 2 * ln["size"] for p in face_lines
    )


def _region(view: View, pad: float) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = view.region
    if pad:
        y1 = view.bbox[3] + 5 * (view.bbox[3] - view.bbox[1])
    return x0 - pad * (x1 - x0), y0, x1 + pad * (x1 - x0), y1


def _inside(ln: dict, region: tuple) -> bool:
    xc, yc = center(ln["bbox"])
    return region[0] <= xc <= region[2] and region[1] <= yc <= region[3] and ln["dir"] == (1, 0)


def _relative_position(view: View, x: float) -> float:
    x0, _, x1, _ = view.region
    cx = center(view.bbox)[0]
    return (x - cx) / ((x1 - cx) if x >= cx else (cx - x0))


def _line_text(ln: dict) -> str:
    return fix_ocr(norm_text(ln["text"])) if ln.get("ocr") else norm_text(ln["text"])


def collect(view: View, lines: list[dict], pad: float = 0.0) -> None:
    region = _region(view, pad)
    skin_lines = [ln for ln in lines if "PEAU" in norm_text(ln["text"])]
    face_lines = [ln for ln in lines if RE_FACE.match(norm_text(ln["text"]))]
    for ln in (ln for ln in lines if _inside(ln, region)):
        xc, yc = center(ln["bbox"])
        u = round(_relative_position(view, xc), 3)
        height = ln["bbox"][3] - ln["bbox"][1]
        for zone, arm, explicit in parse_line(_line_text(ln), _skin_context(ln, skin_lines, face_lines)):
            view.bars.append(Bar(zone, arm, u, yc, height, ln["text"].strip(), ln["bbox"], explicit))


def _rows(views: list[View]) -> list[list[View]]:
    by_row: dict[tuple, list[View]] = {}
    for view in views:
        by_row.setdefault((id(view.page), view.row), []).append(view)
    return list(by_row.values())


def _long_bars(views: list[View]) -> list[Bar]:
    return [b for v in views for b in v.bars if b.zone == "LONG"]


def _assign_layers(longs: list[Bar], split: float) -> None:
    for bar in longs:
        bar.zone = bar.arm.role = "SUP" if bar.y < split else "INF"


def resolve_long(views: list[View]) -> None:
    for row in _rows(views):
        row_split = split_y(_long_bars(row))
        for view in row:
            longs = _long_bars([view])
            split = split_y(longs) or row_split
            if split is not None:
                _assign_layers(longs, split)


def _page_views(page, pad: float, known_ids: frozenset) -> list[View]:
    lines = reread_lines(page) if page.ocr else page.lines
    if not lines:
        return []
    found = page_views(page, lines, page.ocr, known_ids, page.lines if page.ocr else None)
    for view in found:
        collect(view, lines, pad)
    resolve_long(found)
    for view in found:
        view.row_bars = [b for o in found if o is not view and o.row == view.row for b in o.bars]
    return found


def views_of(ctx: Ctx, source: str, pad: float, known_ids: frozenset = frozenset()) -> list[View]:
    return [view for page in ctx.pages_of(source, TYPE) for view in _page_views(page, pad, known_ids)]


def merge_views(views: list[View]) -> dict[str, list[View]]:
    by_beam: dict[str, list[View]] = {}
    for view in views:
        by_beam.setdefault(view.beam, []).append(view)
    out = {}
    for beam, group in by_beam.items():
        elevations = [v for v in group if any(b.zone == "LIG" for b in v.bars)]
        out[beam] = elevations or [max(group, key=lambda v: len(v.bars))]
    return out
