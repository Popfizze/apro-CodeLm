from __future__ import annotations

from itertools import combinations

from ...models import Armature
from .views import Bar, View

SPACING_TOL_MM = 5.0
MAX_COMBINED = 6
CENTRAL_SPAN = 1.0


def key_bars(views: list[View], zone: str) -> list[Bar]:
    return [b for v in views for b in v.bars if b.zone == zone]


def spacing_key(bar: Bar) -> tuple:
    return (bar.arm.diametre, round((bar.arm.espacement_mm or 0) / 5))


def dedupe(bars: list[Bar]) -> list[Bar]:
    seen, out = set(), []
    for bar in bars:
        if spacing_key(bar) not in seen:
            seen.add(spacing_key(bar))
            out.append(bar)
    return out


def _summing_candidates(plan: Bar, shop: list[Bar], pool: list[int]) -> list[int]:
    same_size = (j for j in pool if shop[j].arm.diametre == plan.arm.diametre and shop[j].arm.quantite)
    return sorted(same_size, key=lambda j: abs(shop[j].u - plan.u))


def _best_combination(plan: Bar, shop: list[Bar], candidates: list[int], n: int) -> tuple | None:
    best = None
    for combo in combinations(candidates[:MAX_COMBINED], n):
        if sum(shop[j].arm.quantite for j in combo) != plan.arm.quantite:
            continue
        d = sum(abs(shop[j].u - plan.u) for j in combo) / n
        if best is None or d < best[0]:
            best = (d, combo)
    return best


def _exact_combination(plan: Bar, shop: list[Bar], pool: list[int]) -> list[int] | None:
    candidates = _summing_candidates(plan, shop, pool)
    for n in (1, 2, 3):
        best = _best_combination(plan, shop, candidates, n)
        if best:
            return list(best[1])
    return None


def _exact_pass(plan: list[Bar], shop: list[Bar], order: list[int], assign: dict, used: set) -> None:
    for i in order:
        hit = _exact_combination(plan[i], shop, [j for j in range(len(shop)) if j not in used])
        if hit:
            assign[i] = hit
            used.update(hit)


def _lapped_pass(plan: list[Bar], shop: list[Bar], order: list[int], assign: dict) -> None:
    for i in order:
        if i in assign:
            continue
        hit = _exact_combination(plan[i], shop, list(range(len(shop))))
        if hit:
            assign[i] = hit


def _closest(shop: list[Bar], pool: list[int], u: float) -> int:
    return min(pool, key=lambda j: abs(shop[j].u - u))


def _nearest_pass(plan: list[Bar], shop: list[Bar], left: list[int], assign: dict, used: set) -> None:
    everything = list(range(len(shop)))
    for i in left:
        pool = [j for j in everything if j not in used] or everything
        if pool:
            j = _closest(shop, pool, plan[i].u)
            assign[i] = [j]
            used.add(j)


def align_long(plan: list[Bar], shop: list[Bar]) -> tuple[dict[int, list[int]], list[int]]:
    assign: dict[int, list[int]] = {}
    used: set[int] = set()
    order = sorted(range(len(plan)), key=lambda i: abs(plan[i].u))
    _exact_pass(plan, shop, order, assign, used)
    if not any(j not in used and abs(shop[j].u) <= CENTRAL_SPAN for j in range(len(shop))):
        _lapped_pass(plan, shop, order, assign)
    left = [i for i in range(len(plan)) if i not in assign]
    _nearest_pass(plan, shop, left, assign, used)
    return assign, left


def _same_spacing(plan: Armature, shop: Armature) -> bool:
    if plan.diametre != shop.diametre:
        return False
    if plan.espacement_mm is None:
        return True
    return shop.espacement_mm is not None and abs(plan.espacement_mm - shop.espacement_mm) <= SPACING_TOL_MM


def _spacing_distance(a: Armature, b: Armature) -> float:
    return abs((a.espacement_mm or 0) - (b.espacement_mm or 0))


def _closest_spacing(plan: Armature, shop: list[Bar]) -> int:
    return min(
        range(len(shop)),
        key=lambda j: (shop[j].arm.diametre != plan.diametre, _spacing_distance(shop[j].arm, plan)),
    )


def _closest_plan(shop: Armature, plan: list[Bar]) -> int:
    return min(range(len(plan)), key=lambda i: _spacing_distance(shop, plan[i].arm))


def _first_matches(plan: list[Bar], shop: list[Bar]) -> dict[int, list[int]]:
    assign: dict[int, list[int]] = {i: [] for i in range(len(plan))}
    for j, s in enumerate(shop):
        match = next((i for i, p in enumerate(plan) if _same_spacing(p.arm, s.arm)), None)
        if match is not None:
            assign[match].append(j)
    return assign


def align_spacing(plan: list[Bar], shop: list[Bar]) -> tuple[dict[int, list[int]], list[int]]:
    assign = _first_matches(plan, shop)
    left = [i for i in range(len(plan)) if not assign[i]]
    if shop:
        for i in left:
            assign[i].append(_closest_spacing(plan[i].arm, shop))
    for j in range(len(shop)):
        if plan and not any(j in v for v in assign.values()):
            assign[_closest_plan(shop[j].arm, plan)].append(j)
    return assign, left
