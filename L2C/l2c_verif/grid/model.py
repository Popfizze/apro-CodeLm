from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import pairwise
from statistics import median

RE_NUM = re.compile(r"^\d{1,2}(\.\d)?$")
RE_LET = re.compile(r"^([A-Z])\1?(\.\d)?$")
RE_NUM_SUFFIX = re.compile(r"^(\d{1,2}(?:\.\d)?)[A-Z]$")
RE_LOCATION = re.compile(r"^([A-Z]{1,2}(?:\.\d)?)-(\d{1,2}(?:\.\d)?)$")
RE_SUBLABEL = re.compile(r"^([A-Z]{1,2}|\d{1,2})\.(\d)$")
DEFAULT_SPACING = 150.0


def grid_label(text: str) -> str:
    t = text.strip()
    match = RE_NUM_SUFFIX.match(t)
    return match.group(1) if match else t


def label_value(label: str) -> float:
    match = RE_LET.match(label)
    if not match:
        return float(label)
    base = (ord(label[0]) - ord("A")) + (100 if len(label.split(".")[0]) == 2 else 0)
    return base + (float("0" + match.group(2)) if match.group(2) else 0.0)


def _next_label(base: str) -> str:
    return str(int(base) + 1) if base.isdigit() else chr(ord(base[0]) + 1) * len(base)


def _first_position(lines: list[GridLine], label: str) -> float | None:
    return next((g.pos for g in lines if g.label == label), None)


def line_position(lines: list[GridLine], label: str) -> float | None:
    exact = _first_position(lines, label)
    if exact is not None:
        return exact
    match = RE_SUBLABEL.match(label)
    if not match:
        return None
    base = _first_position(lines, match.group(1))
    following = _first_position(lines, _next_label(match.group(1)))
    if base is None or following is None:
        return None
    return base + int(match.group(2)) / 10 * (following - base)


def _bracketing_lines(lines: list[GridLine], pos: float) -> tuple[GridLine, GridLine] | None:
    whole = [g for g in lines if "." not in g.label]
    before = [g for g in whole if g.pos <= pos]
    after = [g for g in whole if g.pos > pos]
    if not before or not after:
        return None
    return max(before, key=lambda g: g.pos), min(after, key=lambda g: g.pos)


def _sub_label(base: int, decimal: int, numeric: bool) -> str:
    if numeric:
        return f"{base}.{decimal}"
    letter = chr(ord("A") + base - 100) * 2 if base >= 100 else chr(ord("A") + base)
    return f"{letter}.{decimal}"


def interpolated_label(lines: list[GridLine], pos: float, numeric: bool) -> str | None:
    bracket = _bracketing_lines(lines, pos)
    if bracket is None:
        return None
    a, b = bracket
    va, vb = label_value(a.label), label_value(b.label)
    if abs(vb - va) != 1:
        return None
    value = va + (vb - va) * (pos - a.pos) / (b.pos - a.pos)
    base = int(min(va, vb))
    decimal = round((value - base) * 10)
    if decimal <= 0 or decimal >= 10:
        return None
    return _sub_label(base, decimal, numeric)


def _nearest(lines: list[GridLine], pos: float) -> tuple[GridLine | None, float]:
    if not lines:
        return None, float("inf")
    line = min(lines, key=lambda g: abs(g.pos - pos))
    return line, abs(line.pos - pos)


@dataclass
class GridLine:
    label: str
    pos: float
    paired: bool = True


@dataclass
class Grid:
    verticals: list[GridLine] = field(default_factory=list)
    horizontals: list[GridLine] = field(default_factory=list)
    letters_vertical: bool = False

    def cell_label(self, v_label: str, h_label: str) -> str:
        return f"{v_label}-{h_label}" if self.letters_vertical else f"{h_label}-{v_label}"

    @property
    def ok(self) -> bool:
        return len(self.verticals) >= 2 and len(self.horizontals) >= 2

    def position(self, loc: str | None) -> tuple[float, float] | None:
        match = RE_LOCATION.match(re.sub(r"\s+", "", (loc or "").upper()))
        if not match:
            return None
        if self.letters_vertical:
            letter_lines, number_lines = self.verticals, self.horizontals
        else:
            letter_lines, number_lines = self.horizontals, self.verticals
        a, b = line_position(letter_lines, match.group(1)), line_position(number_lines, match.group(2))
        if a is None or b is None:
            return None
        return (a, b) if self.letters_vertical else (b, a)

    def spacing(self) -> float:
        gaps = [q.pos - p.pos for lines in (self.verticals, self.horizontals) for p, q in pairwise(lines)]
        gaps = [g for g in gaps if g > 1]
        return median(gaps) if gaps else DEFAULT_SPACING

    def nearest_vertical(self, x: float) -> tuple[GridLine | None, float]:
        return _nearest(self.verticals, x)

    def nearest_horizontal(self, y: float) -> tuple[GridLine | None, float]:
        return _nearest(self.horizontals, y)

    def locate(self, x: float, y: float) -> tuple[str | None, float]:
        v, dx = self.nearest_vertical(x)
        h, dy = self.nearest_horizontal(y)
        if v is None or h is None:
            return None, float("inf")
        return self.cell_label(v.label, h.label), (dx * dx + dy * dy) ** 0.5

    def locate_precise(self, x: float, y: float, snap: float = 20.0) -> tuple[str | None, float]:
        loc, d = self.locate(x, y)
        if loc is None:
            return loc, d
        v, dx = self.nearest_vertical(x)
        h, dy = self.nearest_horizontal(y)
        vi = interpolated_label(self.verticals, x, numeric=not self.letters_vertical) if dx > snap else None
        hi = interpolated_label(self.horizontals, y, numeric=self.letters_vertical) if dy > snap else None
        rx = 0.0 if vi else dx
        ry = 0.0 if hi else dy
        return self.cell_label(vi or v.label, hi or h.label), (rx * rx + ry * ry) ** 0.5

    def intersections(self):
        for h in self.horizontals:
            for v in self.verticals:
                yield self.cell_label(v.label, h.label), v.pos, h.pos

    def nearest_in_quadrant(self, x: float, y: float, sx: int, sy: int, max_d: float, slack: float = 12.0):
        best = None
        for label, ix, iy in self.intersections():
            dx, dy = ix - x, iy - y
            if (sx and dx * sx < -slack) or (sy and dy * sy < -slack):
                continue
            d = (dx * dx + dy * dy) ** 0.5
            if d <= max_d and (best is None or d < best[1]):
                best = (label, d)
        return best
