from __future__ import annotations

from dataclasses import dataclass, field

from ..blocks import Block
from ..grid import Grid
from ..ingest import PageRef
from ..models import Armature, Item

OCR_CONFIDENCE_FACTOR = 0.8


@dataclass
class Ctx:
    project: str
    pages: list[PageRef]
    blocks: dict[str, list[Block]]
    reads: dict[str, dict] = field(default_factory=dict)
    grids: dict[str, Grid] = field(default_factory=dict)

    def pages_of(self, source: str, type_element: str) -> list[PageRef]:
        return [p for p in self.pages if p.source == source and p.type_element == type_element]

    def read(self, block: Block) -> dict:
        return self.reads.get(block.id) or {"armature": [], "confiance": 0.3, "methode": "regex"}


def _box(bbox, block: Block | None) -> list[float]:
    if bbox is not None:
        return list(bbox)
    return block.bbox if block is not None else [0, 0, 0, 0]


def _reading(ctx: Ctx, block: Block | None, read: dict | None) -> dict:
    if read is not None:
        return read
    return ctx.read(block) if block is not None else {}


def make_item(
    ctx: Ctx,
    page: PageRef,
    *,
    id: str,
    type_element: str,
    block: Block | None = None,
    bbox=None,
    armature: list[Armature] | None = None,
    read: dict | None = None,
    **fields,
) -> Item:
    box = _box(bbox, block)
    reading = _reading(ctx, block, read)
    bars = armature if armature is not None else reading.get("armature", [])
    if reading.get("note"):
        fields["localisation_note"] = "; ".join(
            x for x in (fields.get("localisation_note"), reading["note"]) if x
        )
    confidence = fields.pop("confiance", reading.get("confiance", 0.5))
    method = fields.pop("methode", reading.get("methode", "regex"))
    if getattr(page, "ocr", False):
        confidence, method = round(confidence * OCR_CONFIDENCE_FACTOR, 2), "ocr"
    fields.setdefault("texte_brut", block.text if block is not None else None)
    return Item(
        id=id,
        source=page.source,
        fichier=page.fichier,
        feuillet=page.feuillet,
        page=page.page,
        x=round((box[0] + box[2]) / 2, 1),
        y=round((box[1] + box[3]) / 2, 1),
        type_element=type_element,
        armature=[a.model_copy() for a in bars],
        bbox=[round(v, 1) for v in box],
        confiance=confidence,
        methode=method,
        **fields,
    )
