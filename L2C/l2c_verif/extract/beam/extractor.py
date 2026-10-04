from __future__ import annotations

from ...geometry import union_bbox
from ...models import Armature
from ..base import Ctx, make_item
from .pairing import pair_armatures, solo_armatures
from .views import TYPE, View, merge_views, views_of

CONF_TEXT = 0.8
CONF_OCR = 0.6
CONF_UNSURE = 0.45
CONF_EMPTY = 0.3


def _raw_text(views: list[View]) -> str:
    seen: list[str] = []
    for bar in sorted((b for v in views for b in v.bars), key=lambda b: (b.y, b.u)):
        if bar.text not in seen:
            seen.append(bar.text)
    return f"{views[0].title} | " + " / ".join(seen)


def _item(ctx: Ctx, views: list[View], bars: list[Armature], plan: bool, confidence: float):
    first = views[0]
    page = first.page
    note = (
        f"{'OCR' if first.ocr else 'text'}; {sum(len(v.bars) for v in views)} labels in {len(views)} view(s)"
    )
    return make_item(
        ctx,
        page,
        id=f"{page.feuillet}_{first.beam}_plan" if plan else f"{page.key}_{first.beam}",
        type_element=TYPE,
        bbox=union_bbox([first.bbox] + [b.bbox for b in first.bars]),
        armature=bars,
        read={},
        element=first.title,
        niveau=None,
        localisation=first.beam,
        texte_brut=_raw_text(views),
        confiance=confidence,
        methode="regex",
        localisation_note=note,
    )


def _shop_confidence(views: list[View]) -> float:
    return CONF_OCR if views[0].ocr else CONF_TEXT


def extract(ctx: Ctx):
    plan = merge_views(views_of(ctx, "plan", 0.0))
    shop = merge_views(views_of(ctx, "atelier", 0.2, frozenset(plan)))
    plan_items, shop_items = [], []
    for beam, plan_views in plan.items():
        shop_views = shop.get(beam)
        if shop_views:
            plan_bars, shop_bars, unsure = pair_armatures(plan_views, shop_views)
            plan_items.append(_item(ctx, plan_views, plan_bars, True, CONF_TEXT if plan_bars else CONF_EMPTY))
            shop_confidence = CONF_UNSURE if unsure else _shop_confidence(shop_views)
            shop_items.append(_item(ctx, shop_views, shop_bars, False, shop_confidence))
        else:
            bars = solo_armatures(plan_views)
            plan_items.append(_item(ctx, plan_views, bars, True, CONF_TEXT if bars else CONF_EMPTY))
    for beam, shop_views in shop.items():
        if beam not in plan:
            bars = solo_armatures(shop_views)
            shop_items.append(
                _item(ctx, shop_views, bars, False, _shop_confidence(shop_views) if bars else CONF_EMPTY)
            )
    return plan_items, shop_items
