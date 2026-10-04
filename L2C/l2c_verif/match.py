from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from .compare import compare_armature, compare_items, finding_id, item_gaps, item_notes
from .grid import label_value
from .models import Finding, Item

GEOMETRIC_TOLERANCE = 0.5
RE_LOCATION = re.compile(r"^([A-Z]{1,2}(?:\.\d)?)-(\d{1,2}(?:\.\d)?)$")

Position = Callable[[Item], tuple[float, float, float] | None]
Distance = Callable[[Item, Item], float | None]


def norm_loc(loc: str | None) -> str:
    return re.sub(r"\s+", "", (loc or "").upper())


def loc_values(loc: str | None) -> tuple[float, float] | None:
    match = RE_LOCATION.match(norm_loc(loc))
    if not match:
        return None
    return label_value(match.group(1)), label_value(match.group(2))


def level_key(item: Item) -> tuple:
    return (item.type_element, None if item.type_element == "fondation" else item.niveau)


def item_key(item: Item) -> tuple:
    return (*level_key(item), norm_loc(item.localisation))


def _grid_distance(plan: Item, shop: Item) -> float | None:
    a, b = loc_values(plan.localisation), loc_values(shop.localisation)
    if not a or not b:
        return None
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class GridPositions:
    def __init__(self, plan_items: list[Item], grids: dict):
        self.reference: dict[tuple, object] = {}
        for item in plan_items:
            grid = grids.get(f"{Path(item.fichier).stem}_p{item.page}")
            if grid is not None and grid.ok:
                self.reference.setdefault(level_key(item), grid)

    def __call__(self, item: Item) -> tuple[float, float, float] | None:
        grid = self.reference.get(level_key(item))
        if grid is None:
            return None
        pos = grid.position(item.localisation)
        return None if pos is None else (pos[0], pos[1], grid.spacing())


def _geometric_distance(position: Position) -> Distance:
    def distance(plan: Item, shop: Item) -> float | None:
        a, b = position(plan), position(shop)
        if a is None or b is None:
            return None
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 / a[2]

    return distance


class _Matcher:
    def __init__(self, project: str, shop: list[Item]):
        self.project = project
        self.shop = shop
        self.used: set[str] = set()
        self.findings: list[Finding] = []

    def _take(self, plan: Item, candidates: list[Item], approximate: bool = False) -> None:
        shop = min(candidates, key=lambda s: len(compare_armature(plan.armature, s.armature)[0]))
        self.used.add(shop.id)
        self.findings.append(compare_items(self.project, plan, shop, approximate_location=approximate))

    def same_location(self, plan: list[Item]) -> list[Item]:
        by_key: dict[tuple, list[Item]] = {}
        for shop in self.shop:
            by_key.setdefault(item_key(shop), []).append(shop)
        pending = []
        for item in plan:
            candidates = [s for s in by_key.get(item_key(item), []) if s.id not in self.used]
            if candidates:
                self._take(item, candidates)
            else:
                pending.append(item)
        return pending

    def _available(self, plan: Item) -> list[Item]:
        level = level_key(plan)
        return [s for s in self.shop if s.id not in self.used and level_key(s) == level]

    def _closest(self, plan: Item, distance: Distance, limit: float, approximate: bool) -> list[Item]:
        scored = []
        for shop in self._available(plan):
            d = distance(plan, shop)
            if d is None or d > limit:
                continue
            if not approximate or not item_gaps(plan, shop)[0]:
                scored.append((d, shop))
        best = min((d for d, _ in scored), default=None)
        return [s for d, s in scored if d == best]

    def nearby(self, pending: list[Item], distance: Distance, limit: float, approximate: bool) -> list[Item]:
        unmatched = []
        for plan in pending:
            candidates = self._closest(plan, distance, limit, approximate)
            if candidates:
                self._take(plan, candidates, approximate)
            else:
                unmatched.append(plan)
        return unmatched


def _missing(project: str, plan: Item) -> Finding:
    return Finding(
        id=finding_id(project, plan),
        statut="manquant_atelier",
        type_element=plan.type_element,
        element=plan.localisation,
        niveau=plan.niveau,
        feuillet=plan.feuillet,
        plan_item=plan.id,
        confiance=round(plan.confiance, 2),
        note="; ".join(["aucun élément d'atelier à cette localisation / ce niveau", *item_notes(plan)]),
    )


def _added(project: str, shop: Item, sheet: str) -> Finding:
    return Finding(
        id=f"{project}-{sheet}-{shop.localisation}-atelier",
        statut="ajoute_atelier",
        type_element=shop.type_element,
        element=shop.localisation,
        niveau=shop.niveau,
        feuillet=sheet,
        atelier_item=shop.id,
        confiance=round(shop.confiance, 2),
        note="; ".join(["élément d'atelier sans équivalent au plan", *item_notes(shop)]),
    )


def _number_duplicate_ids(findings: list[Finding]) -> None:
    seen: dict[str, int] = {}
    for finding in findings:
        n = seen.get(finding.id, 0)
        seen[finding.id] = n + 1
        if n:
            finding.id = f"{finding.id}-{n + 1}"


def match_and_compare(
    project: str, plan: list[Item], shop: list[Item], position: Position | None = None
) -> list[Finding]:
    matcher = _Matcher(project, shop)
    pending = matcher.same_location(plan)
    passes: list[tuple[Distance, float, bool]] = [(_grid_distance, 0.25, False), (_grid_distance, 1.0, True)]
    if position is not None:
        passes.append((_geometric_distance(position), GEOMETRIC_TOLERANCE, True))
    for distance, limit, approximate in passes:
        pending = matcher.nearby(pending, distance, limit, approximate)
    findings = matcher.findings + [_missing(project, p) for p in pending]
    sheet_of: dict[tuple, str] = {}
    for item in plan:
        sheet_of.setdefault(level_key(item), item.feuillet)
    findings += [
        _added(project, s, sheet_of[level_key(s)])
        for s in shop
        if s.id not in matcher.used and level_key(s) in sheet_of
    ]
    _number_duplicate_ids(findings)
    return findings
