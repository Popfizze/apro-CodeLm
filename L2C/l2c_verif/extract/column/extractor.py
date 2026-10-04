from __future__ import annotations

from ..base import Ctx
from .plan import plan_items
from .shop import shop_items, split_basements


def extract(ctx: Ctx):
    plan = plan_items(ctx)
    shop = shop_items(ctx, plan)
    split_basements(ctx, plan, shop)
    return plan, shop
