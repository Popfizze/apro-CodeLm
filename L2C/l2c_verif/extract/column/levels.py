from __future__ import annotations

import re
from pathlib import Path

from ...ingest import normalize_level
from ...rebar import norm_text
from ..base import Ctx

RE_BASEMENT_TITLE = re.compile(r"SOUS.?SOL\s*S?(\d)\b")
RE_NUMBERED_BASEMENT = re.compile(r"^SOUS-SOL \d$")
RE_FILE_LEVEL = re.compile(r"NIV\W*([A-Z0-9]+)\s*@")


def plan_levels(ctx: Ctx, type_element: str) -> set[str]:
    return {p.niveau for p in ctx.pages_of("plan", type_element) if p.niveau}


def basement_level(title: str | None) -> str | None:
    match = RE_BASEMENT_TITLE.search(norm_text(title or ""))
    return f"SOUS-SOL {match.group(1)}" if match else None


def _foundation_level(levels: set[str]) -> str | None:
    basements = sorted(lv for lv in levels if RE_NUMBERED_BASEMENT.match(lv))
    if basements:
        return basements[-1]
    return "SOUS-SOL" if "SOUS-SOL" in levels else None


def fit_level(level: str | None, levels: set[str]) -> str | None:
    if level is None or level in levels:
        return level
    if level == "FONDATION":
        return _foundation_level(levels)
    if level.startswith("SOUS-SOL") and "SOUS-SOL" in levels:
        return "SOUS-SOL"
    return level


def _token_level(token: str) -> str | None:
    if token.isdigit():
        return f"NIVEAU {int(token)}"
    if token in ("FDN", "FND"):
        return "FONDATION"
    return normalize_level(token)


def file_level(page) -> str | None:
    match = RE_FILE_LEVEL.search(norm_text(Path(page.fichier).stem))
    return _token_level(match.group(1)) if match else page.niveau
