from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import REPO

LOGO_SVG = REPO / "app" / "assets" / "l2c-logo.svg"
STATUSES = ["conforme", "non_conforme", "manquant_atelier", "ajoute_atelier"]
GAP_STATUSES = ["non_conforme", "manquant_atelier", "ajoute_atelier"]
STATUS_LABEL = {
    "conforme": "Conforme",
    "non_conforme": "Non conforme",
    "manquant_atelier": "Manquant atelier",
    "ajoute_atelier": "Ajouté atelier",
}
STATUS_COLORS = {
    "conforme": ("#2E7A55", "#E7F2EC"),
    "non_conforme": ("#B03A3C", "#F7E8E8"),
    "manquant_atelier": ("#6A5897", "#EEEAF6"),
    "ajoute_atelier": ("#5D6570", "#ECEEF1"),
}
CYAN = "#00A0DB"
INK = "#18161B"
TEXT = "#454545"
BORDER = "#DCDCDC"
BORDER_SOFT = "#ECECEC"
FILL = "#F6F6F6"


def rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def corner_radius(width: float, height: float, radius: float) -> tuple[float, float]:
    return (min(0.5, radius / max(width, 1e-3)), min(0.5, radius / max(height, 1e-3)))


def load_json(path: Path, default, tag: str):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[{tag}] cannot read {path}: {exc}", file=sys.stderr)
        return default
    return data if isinstance(data, type(default)) else default


def load_records(path: Path, tag: str) -> list[dict]:
    return [r for r in load_json(path, [], tag) if isinstance(r, dict)]


def by_id(records: list[dict]) -> dict:
    return {r.get("id"): r for r in records}


def sheet_key(sheet) -> tuple:
    if not sheet:
        return (1, 10**9, "")
    match = re.search(r"(\d+)", str(sheet))
    return (0, int(match.group(1)) if match else 10**8, str(sheet))


def natural_key(text) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text or ""))]
