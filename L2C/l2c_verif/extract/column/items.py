from __future__ import annotations

from ...models import Armature
from ..base import Ctx, make_item

TYPE = "colonne"


def ocr_item(ctx: Ctx, page, loc: str, level: str, box, bars: list[Armature], raw: str, confidence: float):
    return make_item(
        ctx,
        page,
        id=f"{page.key}_{loc}_{level}",
        type_element=TYPE,
        bbox=box,
        armature=bars,
        read={"armature": bars, "confiance": confidence, "methode": "regex"},
        element=loc,
        niveau=level,
        localisation=loc,
        texte_brut=raw,
        localisation_note="lecture OCR du dessin d'atelier" if page.ocr else None,
    )
