from __future__ import annotations

import re

from .models import Armature, Ecart, Finding, Item
from .rebar import mm_str

SPACING_TOL_MM = 5.0
LENGTH_TOL_MM = 25.0
LOW_CONFIDENCE = 0.5
APPROX_CONFIDENCE_CAP = 0.5
UNREAD_CONFIDENCE_CAP = 0.4
MAX_SUMMED_BARS = 6
RE_TYPE_LABEL = re.compile(r"^TYPE\s*([A-Z0-9]+)$")


def _by_role(bars: list[Armature]) -> dict[str, list[Armature]]:
    out: dict[str, list[Armature]] = {}
    for bar in bars:
        out.setdefault(bar.role or "?", []).append(bar)
    return out


def _subset_sums(values: list[int]) -> set[int]:
    return {sum(v for k, v in enumerate(values) if mask >> k & 1) for mask in range(1, 1 << len(values))}


def _diameter_gap(role: str, plan: Armature, shop: list[Armature]) -> Ecart | None:
    sizes = [b.diametre for b in shop if b.diametre]
    if plan.diametre and sizes and plan.diametre not in sizes:
        return Ecart(attribut="diametre", repere=role, plan=plan.diametre, atelier=sizes[0])
    return None


def _comparable_quantities(plan: Armature, shop: list[Armature]) -> list[int]:
    counted = [b for b in shop if b.quantite is not None]
    same_size = [b for b in counted if b.diametre == plan.diametre] or counted
    return [b.quantite for b in same_size][:MAX_SUMMED_BARS]


def _quantity_gap(role: str, plan: Armature, shop: list[Armature]) -> Ecart | None:
    if role == "LIG" or plan.quantite is None:
        return None
    quantities = _comparable_quantities(plan, shop)
    if not quantities or plan.quantite in _subset_sums(quantities):
        return None
    return Ecart(attribut="quantite", repere=role, plan=str(plan.quantite), atelier=str(quantities[0]))


def _spacing_gap(role: str, plan: Armature, shop: list[Armature]) -> tuple[Ecart | None, str | None]:
    spacings = [b.espacement_mm for b in shop if b.espacement_mm is not None]
    if plan.espacement_mm is None:
        return None, None
    if not spacings:
        return None, (f"espacement {role} non indiqué à l'atelier" if role != "LIG" else None)
    if any(abs(plan.espacement_mm - v) <= SPACING_TOL_MM for v in spacings):
        return None, None
    gap = Ecart(
        attribut="espacement_mm", repere=role, plan=mm_str(plan.espacement_mm), atelier=mm_str(spacings[0])
    )
    return gap, None


def _length_gap(role: str, plan: Armature, shop: Armature) -> Ecart | None:
    if plan.longueur_mm is None or shop.longueur_mm is None:
        return None
    if abs(plan.longueur_mm - shop.longueur_mm) <= LENGTH_TOL_MM:
        return None
    return Ecart(
        attribut="longueur_mm", repere=role, plan=mm_str(plan.longueur_mm), atelier=mm_str(shop.longueur_mm)
    )


def _role_gaps(role: str, plan: Armature, shop: list[Armature]) -> tuple[list[Ecart], str | None]:
    spacing, note = _spacing_gap(role, plan, shop)
    gaps = [
        _diameter_gap(role, plan, shop),
        _quantity_gap(role, plan, shop),
        spacing,
        _length_gap(role, plan, shop[0]),
    ]
    return [g for g in gaps if g is not None], note


def compare_armature(plan: list[Armature], shop: list[Armature]) -> tuple[list[Ecart], list[str]]:
    ecarts: list[Ecart] = []
    notes: list[str] = []
    shop_by_role = _by_role(shop)
    for role, plan_bars in _by_role(plan).items():
        shop_bars = shop_by_role.get(role)
        if not shop_bars:
            notes.append(f"barres {role} absentes du dessin d'atelier")
            continue
        gaps, note = _role_gaps(role, plan_bars[0], shop_bars)
        ecarts += gaps
        if note:
            notes.append(note)
    return ecarts, notes


def _type_label(item: Item) -> str | None:
    match = RE_TYPE_LABEL.match((item.element or "").upper())
    return match.group(1) if match else None


def _bar_text(bar: Armature) -> str:
    if bar.quantite and bar.diametre:
        text = f"{bar.quantite}-{bar.diametre}"
    else:
        text = bar.diametre or str(bar.quantite or "")
    if bar.espacement_mm is not None:
        text += f" @{mm_str(bar.espacement_mm)}"
    return f"{bar.role} {text}".strip() if bar.role else text


def armature_text(bars: list[Armature]) -> str:
    return ", ".join(_bar_text(bar) for bar in bars)


def item_gaps(plan: Item, shop: Item) -> tuple[list[Ecart], list[str]]:
    ecarts, notes = compare_armature(plan.armature, shop.armature)
    if not plan.armature and shop.armature:
        ecarts.append(
            Ecart(attribut="armature", repere=None, plan="non indiquée", atelier=armature_text(shop.armature))
        )
    plan_type, shop_type = _type_label(plan), _type_label(shop)
    if plan_type and shop_type and plan_type != shop_type:
        ecarts.insert(
            0, Ecart(attribut="type", repere=None, plan=f"TYPE {plan_type}", atelier=f"TYPE {shop_type}")
        )
    elif plan_type and shop_type and ecarts:
        notes.append(f"même type {plan_type} des deux côtés, mais barres différentes du tableau du plan")
    return ecarts, notes


def _gap_text(e: Ecart) -> str:
    return f"{e.repere + ' ' if e.repere else ''}{e.attribut} {e.plan} / {e.atelier}"


def item_notes(*items: Item) -> list[str]:
    return [
        f"{it.source} : {it.localisation_note}" for it in items if it is not None and it.localisation_note
    ]


def finding_id(project: str, plan: Item) -> str:
    suffix = "" if plan.id.endswith("_plan") else "-" + plan.id.rsplit("_", 1)[-1]
    return f"{project}-{plan.feuillet}-{plan.localisation}{suffix}"


def _capped_confidence(plan: Item, shop: Item, approximate: bool, notes: list[str]) -> float:
    confidence = round(min(plan.confiance, shop.confiance), 2)
    if plan.armature and not shop.armature:
        notes.append("armature non lue d'un côté")
        confidence = min(confidence, UNREAD_CONFIDENCE_CAP)
    if approximate:
        notes.insert(0, f"localisation approximative : l'atelier indique {shop.localisation}")
        confidence = min(confidence, APPROX_CONFIDENCE_CAP)
    return confidence


def _retained_gaps(ecarts: list[Ecart], confidence: float, notes: list[str]) -> list[Ecart]:
    if confidence >= LOW_CONFIDENCE:
        return ecarts
    notes.append(f"association ou lecture peu fiable (confiance {confidence:.2f})")
    if ecarts:
        notes.append("écart lu non retenu : " + ", ".join(_gap_text(e) for e in ecarts))
    return []


def compare_items(project: str, plan: Item, shop: Item, approximate_location: bool = False) -> Finding:
    ecarts, notes = item_gaps(plan, shop)
    confidence = _capped_confidence(plan, shop, approximate_location, notes)
    ecarts = _retained_gaps(ecarts, confidence, notes)
    if notes or ecarts:
        notes += item_notes(plan, shop)
    return Finding(
        id=finding_id(project, plan),
        statut="non_conforme" if ecarts else "conforme",
        type_element=plan.type_element,
        element=plan.localisation,
        niveau=plan.niveau,
        feuillet=plan.feuillet,
        plan_item=plan.id,
        atelier_item=shop.id,
        ecarts=ecarts,
        confiance=confidence,
        note="; ".join(dict.fromkeys(notes)) or None,
    )
