from __future__ import annotations

from . import beam, column, foundation, slab, wall
from .base import Ctx

MODULES = [foundation, column, wall, slab, beam]


def implemented_types() -> set[str]:
    return {m.TYPE for m in MODULES}


def run_all(ctx: Ctx):
    plan, shop = [], []
    for module in MODULES:
        plan_items, shop_items = module.extract(ctx)
        plan.extend(plan_items)
        shop.extend(shop_items)
    return plan, shop
