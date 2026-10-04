from __future__ import annotations

from ...geometry import union_bbox
from ...models import Armature
from ..base import Ctx, make_item
from .annotations import plan_annotations, shop_annotations
from .pairing import pair_annotations
from .placement import TYPE, collect

DOUBT_FR = {
    "ADD. bars in the stack": "barres ADD. dans la pile",
    "revision count (N + / + N) in the stack": "nombre révisé (N + / + N) dans la pile",
    "loosely stacked lines": "lignes mal empilées",
    "revision cloud around the stack": "nuage de révision autour de la pile",
    "another M.B. stack adjacent": "autre pile M.B. adjacente",
    "text between two columns": "texte entre deux colonnes",
    "competing shop annotation nearby": "autre annotation d'atelier à proximité",
    "both numbers differ": "les deux nombres diffèrent",
    "texts far apart": "textes éloignés",
    "no column symbol at the nearest intersection": "pas de symbole de colonne à l'intersection",
    "orphan callout lines next to the stack": "lignes de barres isolées à côté de la pile",
}
DOUBTFUL_CONFIDENCE = 0.45


def _armature(annotations: list[dict]) -> list[Armature]:
    bars = []
    for a in sorted(annotations, key=lambda a: a["role"]):
        bars.append(Armature(role=a["role"], repere=a["role"], diametre=a["size"], quantite=a["n"]))
        bars.append(Armature(role=a["role"] + " MB", repere=a["role"] + " MB", quantite=a["m"]))
    return bars


def _score_confidence(worst: float) -> float:
    if worst <= 0.35:
        return 0.9
    return 0.75 if worst <= 0.6 else 0.55


def _note(doubts: list[str], worst: float) -> str:
    prefix = f"à vérifier : {', '.join(DOUBT_FR.get(w, w) for w in doubts)}; " if doubts else ""
    return prefix + f"annotations de bande, pire score d'association {worst:.2f} × maille"


def _make(ctx: Ctx, side: str, level: str, loc: str, annotations: list[dict]):
    by_page: dict[str, list] = {}
    for a in annotations:
        by_page.setdefault(a["page"].key, []).append(a)
    main = max(by_page.values(), key=len)
    page = main[0]["page"]
    worst = max(a["score"] for a in annotations)
    doubts = list(dict.fromkeys(w for a in annotations for w in a.get("weak", [])))
    ordered = sorted(annotations, key=lambda a: a["role"])
    return make_item(
        ctx,
        page,
        id=f"{page.feuillet}_{loc}_plan" if side == "plan" else f"{page.key}_{loc}_{level}",
        type_element=TYPE,
        bbox=union_bbox(a["bbox"] for a in main),
        armature=_armature(annotations),
        read={},
        element=loc,
        niveau=level,
        localisation=loc,
        confiance=DOUBTFUL_CONFIDENCE if doubts else _score_confidence(worst),
        methode="regex",
        texte_brut=" | ".join(f"{a['role']}: {a['text']}" for a in ordered),
        localisation_note=_note(doubts, worst),
    )


def _cells(plan: list[dict], shop: list[dict]) -> dict[tuple, list]:
    cells: dict[tuple, list] = {}
    for level in sorted({a["level"] for a in plan + shop}):
        level_plan = [a for a in plan if a["level"] == level]
        level_shop = [a for a in shop if a["level"] == level]
        for p, s in pair_annotations(level_plan, level_shop):
            reference = p or s
            cells.setdefault((level, reference["loc"], reference["axis"]), []).append((p, s))
    return cells


def _grouped(cells: dict[tuple, list]) -> tuple[dict, dict]:
    plan_groups: dict[tuple, list] = {}
    shop_groups: dict[tuple, list] = {}
    for (level, loc, axis), pairs in cells.items():
        pairs.sort(key=lambda pair: (pair[0] or pair[1])["perp"])
        for k, (p, s) in enumerate(pairs):
            role = f"INTEG {axis}" + (str(k + 1) if k else "")
            for annotation, groups in ((p, plan_groups), (s, shop_groups)):
                if annotation is not None:
                    annotation["role"] = role
                    groups.setdefault((level, loc), []).append(annotation)
    return plan_groups, shop_groups


def extract(ctx: Ctx):
    plan = collect(ctx, "plan", plan_annotations)
    shop = collect(ctx, "atelier", shop_annotations)
    shop_levels = {a["level"] for a in shop}
    plan = [a for a in plan if a["level"] in shop_levels]
    plan_groups, shop_groups = _grouped(_cells(plan, shop))
    plan_items = [_make(ctx, "plan", lvl, loc, anns) for (lvl, loc), anns in sorted(plan_groups.items())]
    shop_items = [_make(ctx, "atelier", lvl, loc, anns) for (lvl, loc), anns in sorted(shop_groups.items())]
    return plan_items, shop_items
