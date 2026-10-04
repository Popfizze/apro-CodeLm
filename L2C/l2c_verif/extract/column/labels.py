from __future__ import annotations

import re
from statistics import median

from ...geometry import center
from ...grid import RE_LET, RE_NUM, Grid, GridLine, grid_label
from ...grid.detect import cluster
from ...rebar import norm_text
from ..base import Ctx

LABEL_SIZE_TOLERANCE = 0.15
MIN_ONE_SIDED_LABELS = 3
MAX_VARIANTS = 64
LETTER_FIXES = {"0": "O", "1": "IT", "7": "T", "5": "S", "9": "S", "8": "B", "2": "Z", "6": "G", "4": "A"}
NUMBER_FIXES = {
    "O": "0",
    "D": "0",
    "Q": "0",
    "U": "0",
    "I": "1",
    "L": "1",
    "T": "1",
    "J": "1",
    "S": "59",
    "B": "8",
    "Z": "2",
    "G": "6",
    "A": "4",
}
RE_PRIMED = re.compile(r"^[A-Z]'$")
RE_SUB_LABEL = re.compile(r"^(.+)\.(\d)$")
RE_LOCATION = re.compile(r"^([A-Z]{1,2}(?:\.\d)?)-(\d{1,2}(?:\.\d)?)$")


def horizontal_lines(page) -> list[dict]:
    return [ln for ln in page.lines if tuple(ln["dir"]) == (1, 0)]


def _missing_kind(grid: Grid, has_horizontals: bool):
    if has_horizontals:
        return RE_LET if grid.letters_vertical else RE_NUM
    return RE_NUM if grid.letters_vertical else RE_LET


def _label_positions(lines: list[dict], kind, size: float) -> list[tuple[str, float, float]]:
    out = []
    for ln in lines:
        label = grid_label(ln["text"])
        if kind.match(label) and abs(ln["size"] - size) <= LABEL_SIZE_TOLERANCE * size:
            out.append((label, *center(ln["bbox"])))
    return out


def _new_lines(band: list[tuple], pos_axis: int) -> list[GridLine]:
    seen, added = set(), []
    for candidate in sorted(band, key=lambda c: c[pos_axis]):
        if candidate[0] not in seen:
            seen.add(candidate[0])
            added.append(GridLine(candidate[0], candidate[pos_axis], paired=False))
    return added


def _one_sided(grid: Grid | None) -> bool | None:
    if grid is None or grid.ok:
        return None
    has_horizontals = len(grid.horizontals) >= 2
    return None if has_horizontals == (len(grid.verticals) >= 2) else has_horizontals


def _densest_band(page, grid: Grid, has_horizontals: bool) -> list[tuple]:
    present = {g.label for g in (grid.horizontals if has_horizontals else grid.verticals)}
    lines = horizontal_lines(page)
    sizes = [ln["size"] for ln in lines if grid_label(ln["text"]) in present]
    if not sizes:
        return []
    labels = _label_positions(lines, _missing_kind(grid, has_horizontals), median(sizes))
    band_axis = 2 if has_horizontals else 1
    bands = cluster([(c[band_axis], c) for c in labels], 3.0)
    return max(bands, key=lambda b: len({c[0] for c in b}), default=[])


def complete_grid(page, grid: Grid | None) -> Grid | None:
    has_horizontals = _one_sided(grid)
    if has_horizontals is None:
        return grid
    best = _densest_band(page, grid, has_horizontals)
    if len({c[0] for c in best}) < MIN_ONE_SIDED_LABELS:
        return grid
    if has_horizontals:
        added = _new_lines(best, 1)
        return Grid(
            verticals=added, horizontals=list(grid.horizontals), letters_vertical=grid.letters_vertical
        )
    added = _new_lines(best, 2)
    return Grid(verticals=list(grid.verticals), horizontals=added, letters_vertical=grid.letters_vertical)


def usable_grid(ctx: Ctx, page) -> Grid | None:
    grid = ctx.grids.get(page.key)
    if grid is not None and not grid.ok:
        fixed = complete_grid(page, grid)
        if fixed is not grid and fixed.ok:
            ctx.grids[page.key] = fixed
            return fixed
    return grid


def _reference_labels(lines: list[dict], grid: Grid) -> list[dict]:
    positions = {g.label: g.pos for g in grid.verticals}
    return [
        ln
        for ln in lines
        if grid_label(ln["text"]) in positions
        and abs(center(ln["bbox"])[0] - positions[grid_label(ln["text"])]) < 4
    ]


def _primed_label(ln: dict, size: float) -> str | None:
    label = norm_text(ln["text"])
    if not RE_PRIMED.match(label) or abs(ln["size"] - size) > LABEL_SIZE_TOLERANCE * size:
        return None
    return label


def _label_bands(lines: list[dict], grid: Grid) -> tuple[float, set[int]] | None:
    references = _reference_labels(lines, grid)
    if not references:
        return None
    return median(ln["size"] for ln in references), {round(center(ln["bbox"])[1]) for ln in references}


def primed_verticals(page, grid: Grid | None) -> list[GridLine]:
    if grid is None or not grid.ok or not grid.letters_vertical:
        return []
    lines = horizontal_lines(page)
    reference = _label_bands(lines, grid)
    if reference is None:
        return []
    size, bands = reference
    out, seen = [], set()
    for ln in lines:
        label = _primed_label(ln, size)
        x, y = center(ln["bbox"])
        if label is not None and label not in seen and any(abs(y - b) < 3 for b in bands):
            seen.add(label)
            out.append(GridLine(label, x, paired=False))
    return out


class PrimedGrid:
    def __init__(self, grid: Grid, primes: list[GridLine]):
        self.grid, self.primes = grid, primes

    def __getattr__(self, name):
        return getattr(self.grid, name)

    def _prime_hit(self, x: float, y: float):
        prime = min(self.primes, key=lambda g: abs(g.pos - x))
        _, dx = self.grid.nearest_vertical(x)
        h, dy = self.grid.nearest_horizontal(y)
        if h is None or abs(prime.pos - x) >= dx:
            return None
        return self.grid.cell_label(prime.label, h.label), (abs(prime.pos - x) ** 2 + dy**2) ** 0.5

    def locate(self, x: float, y: float):
        return self._prime_hit(x, y) or self.grid.locate(x, y)

    def locate_precise(self, x: float, y: float, snap: float = 20.0):
        return self._prime_hit(x, y) or self.grid.locate_precise(x, y, snap)


def _label_ok(label: str, valid: set[str]) -> bool:
    if label in valid:
        return True
    match = RE_SUB_LABEL.match(label)
    return bool(match and match.group(1) in valid)


def _variants(raw: str, fixes: dict[str, str]) -> set[str] | None:
    options = {""}
    for ch in raw:
        alternatives = dict.fromkeys(fixes.get(ch, "") + ch)
        options = {o + a for o in options for a in alternatives}
        if len(options) > MAX_VARIANTS:
            return None
    return options


def _label_candidates(raw: str, valid: set[str], fixes: dict[str, str]) -> set[str]:
    raw = re.sub(r"^(.+\.\d)\d$", r"\1", raw)
    if _label_ok(raw, valid):
        return {raw}
    if "'" in raw:
        return set()
    forms = [raw] + ([f"{raw[0]}.{raw[1]}"] if len(raw) == 2 else [])
    for form in forms:
        options = _variants(form, fixes)
        if options is None:
            return set()
        hits = {o for o in options if _label_ok(o, valid)}
        if hits:
            return hits
    return set()


def normalize_location(
    letter: str, number: str, labels: tuple[set[str], set[str]], preferred: set[str] | None = None
) -> str | None:
    letters, numbers = labels
    if not letters or not numbers:
        return None
    combos = {
        f"{a}-{b}"
        for a in _label_candidates(letter.replace(" ", ""), letters, LETTER_FIXES)
        for b in _label_candidates(number.replace(" ", ""), numbers, NUMBER_FIXES)
    }
    if len(combos) > 1 and preferred:
        combos &= preferred
    return combos.pop() if len(combos) == 1 else None


def location_fixed(letter: str, number: str, loc: str) -> bool:
    return loc != f"{letter.replace(' ', '')}-{number.replace(' ', '')}"


def plan_grid_labels(ctx: Ctx, type_element: str, items=()) -> tuple[set[str], set[str]]:
    letters, numbers = set(), set()
    for page in ctx.pages_of("plan", type_element):
        grid = usable_grid(ctx, page)
        if grid is None or not grid.ok:
            continue
        for g in grid.verticals + grid.horizontals:
            (letters if RE_LET.match(g.label) else numbers).add(g.label)
        letters.update(g.label for g in primed_verticals(page, grid))
    for item in items:
        match = RE_LOCATION.match(item.localisation or "")
        if match:
            letters.add(match.group(1))
            numbers.add(match.group(2))
    return letters, numbers
