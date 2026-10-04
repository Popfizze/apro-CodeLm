from __future__ import annotations

from ...models import Armature
from .align import align_long, align_spacing, dedupe, key_bars, spacing_key
from .views import Bar, View

ZONES_LONG = ("SUP", "INF")
ZONES_SPACING = ("LIG", "PEAU", "LIG ADD")
ZONES_UNPAIRED = ("LONG", "LIG U", "ADD")
FAR_FROM_CENTER = 0.6


def role_name(zone: str, k: int) -> str:
    return zone if k == 0 else f"{zone} {k + 1}"


def copy_bar(bar: Bar, role: str) -> Armature:
    armature = bar.arm.model_copy()
    armature.role = role
    if armature.repere in (None, bar.zone, "LONG"):
        armature.repere = role
    return armature


def _long_zone(plan_views: list[View], shop_views: list[View], zone: str) -> tuple:
    plan = sorted(key_bars(plan_views, zone), key=lambda b: abs(b.u))
    shop = key_bars(shop_views, zone)
    assign, left = align_long(plan, shop)
    off_center = bool(left) and all(abs(plan[i].u) > FAR_FROM_CENTER for i in left)
    return plan, shop, assign, bool(plan and not shop) or off_center


def _by_frequency(bars: list[Bar]) -> list[Bar]:
    counts: dict[tuple, int] = {}
    for bar in bars:
        counts[spacing_key(bar)] = counts.get(spacing_key(bar), 0) + 1
    return sorted(dedupe(bars), key=lambda b: -counts[spacing_key(b)])


def _row_bars(shop_views: list[View], zone: str) -> list[Bar]:
    return [b for v in shop_views for b in v.row_bars if b.zone == zone]


def _spacing_zone(plan_views: list[View], shop_views: list[View], zone: str) -> tuple:
    plan = key_bars(plan_views, zone)
    plan = _by_frequency(plan) if zone == "LIG" else dedupe(plan)
    shop = key_bars(shop_views, zone)
    may_borrow = zone != "LIG ADD"
    borrowed = bool(plan) and not shop and may_borrow
    if borrowed:
        shop = _row_bars(shop_views, zone)
        borrowed = bool(shop)
    assign, left = align_spacing(plan, shop)
    unsure = (borrowed and bool(left)) or (bool(plan) and not shop and may_borrow)
    return plan, shop, assign, unsure


def _zone_armatures(zone: str, plan: list[Bar], shop: list[Bar], assign: dict) -> tuple[list, list]:
    roles = {i: role_name(zone, i) for i in range(len(plan))}
    plan_bars = [copy_bar(p, roles[i]) for i, p in enumerate(plan)]
    shop_bars, given = [], set()
    for i, indexes in assign.items():
        for j in indexes:
            shop_bars.append(copy_bar(shop[j], roles[i]))
            given.add(j)
    shop_bars += [copy_bar(s, f"{zone} AUTRE") for j, s in enumerate(shop) if j not in given]
    return plan_bars, shop_bars


def pair_armatures(
    plan_views: list[View], shop_views: list[View]
) -> tuple[list[Armature], list[Armature], bool]:
    plan_bars: list[Armature] = []
    shop_bars: list[Armature] = []
    unsure = False
    for zone in ZONES_LONG + ZONES_SPACING:
        pairing = _long_zone if zone in ZONES_LONG else _spacing_zone
        plan, shop, assign, zone_unsure = pairing(plan_views, shop_views, zone)
        zone_plan, zone_shop = _zone_armatures(zone, plan, shop, assign)
        plan_bars += zone_plan
        shop_bars += zone_shop
        unsure = unsure or zone_unsure
    for zone in ZONES_UNPAIRED:
        plan_bars.extend(copy_bar(b, zone) for b in key_bars(plan_views, zone))
        shop_bars.extend(copy_bar(b, zone) for b in key_bars(shop_views, zone))
    return plan_bars, shop_bars, unsure or bool(key_bars(plan_views, "LONG"))


def solo_armatures(views: list[View]) -> list[Armature]:
    out = []
    for zone in ZONES_LONG + ZONES_SPACING + ZONES_UNPAIRED:
        bars = key_bars(views, zone)
        if zone in ZONES_SPACING:
            bars = dedupe(bars)
        out.extend(
            copy_bar(b, role_name(zone, k) if zone in ZONES_LONG else zone) for k, b in enumerate(bars)
        )
    return out
