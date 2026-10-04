from __future__ import annotations

import re
from itertools import pairwise

from ...geometry import center
from ...ingest import normalize_level
from ...rebar import norm_text
from ..base import Ctx, make_item
from .cards import axis_cards
from .items import TYPE
from .labels import plan_grid_labels
from .levels import basement_level, file_level, fit_level, plan_levels
from .schedule import schedule_items
from .slash import slash_cards

RE_HEAD = re.compile(r"^[A-Z]{1,2}(?:\.\d)?-\d{1,2}(?:\.\d)?(?:-\d{1,2}(?:\.\d)?)?$")
RE_LEVEL_WORD = re.compile(r"NIVEAU|REZ|SOUS|TOIT|TREFOND|RADIER|EMPATTEMENT")
RE_PART = re.compile(r"PARTIE\s*(\d+)")
RE_NUMBERED_BASEMENT = re.compile(r"^SOUS-SOL \d$")
LEVEL_MARGIN = 0.08
DEFAULT_PITCH = 120.0
HEADER_ROW_TOLERANCE = 15.0


def _margin_level(text: str) -> str | None:
    if text.startswith("RADIER"):
        return "RADIER"
    return normalize_level(text) if RE_LEVEL_WORD.search(text) else None


def _page_levels(page) -> list[tuple[str, float]]:
    out = []
    for ln in page.lines:
        if ln["bbox"][0] >= page.width * LEVEL_MARGIN:
            continue
        text = norm_text(ln["text"])
        level = None if text.startswith("EL") else _margin_level(text)
        if level:
            out.append((level, ln["bbox"][1]))
    return sorted(out, key=lambda z: z[1])


def _headers(page) -> list[tuple[str, float, float]]:
    heads = []
    for ln in page.lines:
        text = norm_text(ln["text"])
        if RE_HEAD.match(text) and ln["size"] >= 8:
            heads.append((text, *center(ln["bbox"])))
    return heads


def _header_rows(heads: list[tuple]) -> list[list[tuple]]:
    rows: list[list[tuple]] = []
    for head in sorted(heads, key=lambda h: h[2]):
        if rows and abs(rows[-1][-1][2] - head[2]) <= HEADER_ROW_TOLERANCE:
            rows[-1].append(head)
        else:
            rows.append([head])
    return rows


def _header_pitch(heads: list[tuple]) -> float:
    gaps = []
    for row in _header_rows(heads):
        gaps += [b - a for a, b in pairwise(sorted(h[1] for h in row)) if b - a > 1]
    return min(gaps, default=DEFAULT_PITCH)


def _header_for(heads: list[tuple], cx: float, cy: float, pitch: float, below: bool):
    same_column = [h for h in heads if abs(h[1] - cx) <= pitch * 0.75]
    pool = [h for h in same_column if (h[2] > cy) == below] or same_column
    return min(pool, key=lambda h: abs(h[2] - cy)) if pool else None


def _table_candidates(ctx: Ctx, page, heads: list[tuple], levels: list[tuple]) -> list[tuple]:
    pitch = _header_pitch(heads)
    headers_below = not any(h[2] < page.height * 0.35 for h in heads)
    found = []
    for block in ctx.blocks.get(page.key, []):
        if not any(norm_text(t).startswith("VERT") for t in block.texts):
            continue
        cx, cy = block.center
        head = _header_for(heads, cx, cy, pitch, headers_below)
        lower = [lv for lv in levels if lv[1] > cy] if head is not None else []
        if lower:
            found.append((page, block, head[0], lower[0][0]))
    return found


def _part_rank(fichier: str) -> int:
    match = RE_PART.search(norm_text(fichier))
    return int(match.group(1)) if match else 0


def _plan_locations(ctx: Ctx, plan_items, level: str) -> set[str]:
    sheets = {p.feuillet for p in ctx.pages_of("plan", TYPE) if basement_level(p.titre) == level}
    return {it.localisation for it in plan_items if it.niveau == level or it.feuillet in sheets}


def _known_levels(ctx: Ctx) -> set[str]:
    basements = {
        basement_level(p.titre)
        for p in ctx.pages_of("plan", TYPE)
        if p.niveau == "SOUS-SOL" and basement_level(p.titre)
    }
    return plan_levels(ctx, TYPE) | basements


def _ocr_layout_items(ctx: Ctx, pages, plan_items) -> list:
    if not pages:
        return []
    labels, levels = plan_grid_labels(ctx, TYPE, plan_items), _known_levels(ctx)
    items, seen = [], set()
    for page in pages:
        raw_level = file_level(page)
        level = fit_level(raw_level, levels)
        if level is None:
            continue
        preferred = _plan_locations(ctx, plan_items, level)
        found = slash_cards(ctx, page, labels, level, preferred) or schedule_items(
            ctx, page, labels, level, preferred
        )
        for item in found:
            if (item.localisation, raw_level) not in seen:
                seen.add((item.localisation, raw_level))
                items.append(item)
    return items


def _table_items(ctx: Ctx, candidates: list[tuple]) -> list:
    items, seen = [], set()
    for page, block, loc, level in sorted(candidates, key=lambda c: -_part_rank(c[0].fichier)):
        if (loc, level) in seen:
            continue
        seen.add((loc, level))
        items.append(
            make_item(
                ctx,
                page,
                id=f"{page.key}_{loc}_{level}",
                type_element=TYPE,
                block=block,
                element=loc,
                niveau=level,
                localisation=loc,
            )
        )
    return items


def _page_candidates(ctx: Ctx, page) -> list[tuple]:
    heads, levels = _headers(page), _page_levels(page)
    return _table_candidates(ctx, page, heads, levels) if heads and levels else []


def _classify_pages(ctx: Ctx) -> tuple[list, list, list]:
    candidates, cards, unread = [], [], []
    for page in ctx.pages_of("atelier", TYPE):
        page_cards = axis_cards(ctx, page)
        found = [] if page_cards else _page_candidates(ctx, page)
        cards.extend(page_cards)
        candidates.extend(found)
        if not page_cards and not found:
            unread.append(page)
    return candidates, cards, unread


def _add_new(items: list, extra, seen: set) -> None:
    for item in extra:
        if (item.localisation, item.niveau) not in seen:
            seen.add((item.localisation, item.niveau))
            items.append(item)


def shop_items(ctx: Ctx, plan_items=()) -> list:
    candidates, cards, unread = _classify_pages(ctx)
    items = _table_items(ctx, candidates)
    seen = {(it.localisation, it.niveau) for it in items}
    _add_new(items, cards, seen)
    items.extend(
        it for it in _ocr_layout_items(ctx, unread, plan_items) if (it.localisation, it.niveau) not in seen
    )
    return items


def split_basements(ctx: Ctx, plan: list, shop: list) -> None:
    shop_basements = {it.niveau for it in shop if RE_NUMBERED_BASEMENT.match(it.niveau or "")}
    if not shop_basements:
        return
    sheet_level = {
        p.feuillet: basement_level(p.titre) for p in ctx.pages_of("plan", TYPE) if p.niveau == "SOUS-SOL"
    }
    for item in plan:
        if item.niveau == "SOUS-SOL" and sheet_level.get(item.feuillet) in shop_basements:
            item.niveau = sheet_level[item.feuillet]
