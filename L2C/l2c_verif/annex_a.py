from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from .style import load_json

PLAN_FILE = "annexe_a_plan.json"
ATELIER_FILE = "annexe_a_atelier.json"
TAG = "annex_a"

Number = int | float


def _int_if_integral(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class AnnexArmature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repere: str | None
    diametre: str | None
    quantite: int | None
    espacement_mm: Number | None
    longueur_mm: Number | None

    @field_validator("espacement_mm", "longueur_mm")
    @classmethod
    def _clean_number(cls, value):
        return _int_if_integral(value)


class AnnexItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: Literal["plan", "atelier"]
    fichier: str
    feuillet: str | None
    page: int
    x: float
    y: float
    type_element: Literal["fondation", "poutre", "mur", "colonne", "dalle"]
    element: str | None
    armature: list[AnnexArmature]


ITEM_KEYS = list(AnnexItem.model_fields)
ARMATURE_KEYS = list(AnnexArmature.model_fields)


def _rounded(value):
    return round(float(value), 2) if isinstance(value, int | float) else value


def _bars(raw: dict) -> list[dict]:
    return [
        {k: bar.get(k) for k in ARMATURE_KEYS} for bar in (raw.get("armature") or []) if isinstance(bar, dict)
    ]


def to_annex_item(raw: dict, source: str, sheet_by_atelier_id: dict[str, str] | None = None) -> AnnexItem:
    record = {k: raw.get(k) for k in ITEM_KEYS}
    record["source"] = record["source"] or source
    record["armature"] = _bars(raw)
    if record["feuillet"] is None and sheet_by_atelier_id:
        record["feuillet"] = sheet_by_atelier_id.get(record["id"])
    record["x"], record["y"] = _rounded(record["x"]), _rounded(record["y"])
    return AnnexItem.model_validate(record)


def _convert(items: list[dict], source: str, sheet_map: dict[str, str] | None = None) -> list[dict]:
    out = []
    for raw in items:
        try:
            out.append(to_annex_item(raw, source, sheet_map).model_dump(mode="json"))
        except ValidationError as exc:
            print(
                f"[{TAG}] skipped {source} item {raw.get('id')!r}: {exc.error_count()} error(s)",
                file=sys.stderr,
            )
    return out


def export_annex_a(out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    plan = load_json(out_dir / "items_plan.json", [], TAG)
    shop = load_json(out_dir / "items_atelier.json", [], TAG)
    findings = load_json(out_dir / "findings.json", [], TAG)
    sheet_map = {
        f["atelier_item"]: f["feuillet"]
        for f in findings
        if isinstance(f, dict) and f.get("atelier_item") and f.get("feuillet")
    }
    written = []
    for name, items, source, sheets in (
        (PLAN_FILE, plan, "plan", None),
        (ATELIER_FILE, shop, "atelier", sheet_map),
    ):
        path = out_dir / name
        path.write_text(
            json.dumps(_convert(items, source, sheets), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written.append(path)
    return written
