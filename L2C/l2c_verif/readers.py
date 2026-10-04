from __future__ import annotations

import re

from .blocks import Block
from .llm import LlmBar, ground_bar, to_armature
from .models import Armature
from .rebar import ROLE_ALIASES, norm_text, parse_line, parse_lines

RE_MARK_HINT = re.compile(
    r"(?<![\dA-Z])\d{2}(?!X\d)[A-Z]{1,3}\d|\b(?:ATT|SUPPORT|EPIN|ETRI|LIG|GOUJ)[A-Z.\-]*\s*:\s*\d"
)
RE_SIZE_HINT = re.compile(r"(?<![\dA-Z])\d{2}\s?M(?![A-Z])")
RE_LINE_LABEL = re.compile(r"^([A-Z]{2,}(?:-[A-Z]{2,})?)\.?\s*(?::|\s\d)")
AGREEMENT_FIELDS = ("quantite", "diametre", "espacement")
MERGE_RULE = "regex conservée; IA = ajout de barres ancrées sur une ligne non lue par regex"
MAX_EXAMPLES = 30
SCANNER_STATS = (
    ("n_unique_texts_sent", "unique_blocks", 0),
    ("n_batches", "batches", 0),
    ("batch_size", "batch_size", None),
    ("n_valid_json_first_try", "valid_json_first_try", 0),
    ("n_retries", "retries", 0),
    ("n_failures", "failures", 0),
    ("n_ungrounded_retries", "ungrounded_retries", 0),
    ("n_ungrounded_values", "ungrounded_values", 0),
)


def looks_like_rebar(text: str) -> bool:
    t = norm_text(text)
    if RE_MARK_HINT.search(t):
        return True
    return bool(RE_SIZE_HINT.search(t)) and re.search(r"\d", RE_SIZE_HINT.sub(" ", t)) is not None


def line_role(text: str) -> str | None:
    match = RE_LINE_LABEL.match(norm_text(text))
    if not match:
        return None
    return ROLE_ALIASES.get(match.group(1), match.group(1))


def _column_role(header: str) -> str | None:
    if "LONG" in header:
        return "LONG"
    if "TRANS" in header:
        return "TRAN"
    return header.replace(".", "").strip() or None


def _nearest_index(values: list[float], x: float) -> int:
    return min(range(len(values)), key=lambda i: abs(values[i] - x))


def _table_row_read(block: Block) -> list[Armature]:
    header_x = block.meta["header_x"]
    headers = [norm_text(h) for h in block.meta["header_cells"]]
    out = []
    for ln in block.lines:
        bars = parse_line(ln["text"])
        role = _column_role(headers[_nearest_index(header_x, ln["bbox"][0])]) if bars else None
        for armature in bars:
            armature.role = role
            armature.repere = role
        out.extend(bars)
    return out


def regex_read(block: Block) -> list[Armature]:
    if block.kind == "table_row":
        return _table_row_read(block)
    return parse_lines(block.texts)


def unparsed_lines(block: Block) -> list[int]:
    return [i for i, t in enumerate(block.texts) if looks_like_rebar(t) and not parse_line(t)]


def needs_llm(block: Block) -> bool:
    if block.page.source == "plan" and block.page.type_element == "colonne":
        return False
    return bool(unparsed_lines(block))


def _covered(armature: Armature, known: list[Armature]) -> bool:
    return any(
        r.diametre == armature.diametre and (r.quantite or 0) == (armature.quantite or 0) for r in known
    )


def _grounded_line(bar: LlmBar, texts: list[str], unparsed: set[int]) -> tuple[int | None, str | None]:
    index, failures = ground_bar(bar, texts)
    if index is None:
        return None, "non ancrée: " + ", ".join(failures)
    if index not in unparsed:
        return None, f"ligne déjà lue par regex: {texts[index][:40]}"
    return index, None


def _apply_line_role(armature: Armature, bar: LlmBar, line: str) -> None:
    role = line_role(line)
    if role:
        armature.role = role
        if not (bar.repere or "").strip():
            armature.repere = role


def _llm_additions(block: Block, llm: dict, regex_bars: list[Armature]) -> tuple[list[Armature], list[str]]:
    texts, unparsed = block.texts, set(unparsed_lines(block))
    added: list[Armature] = []
    rejected: list[str] = []
    for raw in (llm.get("raw") or {}).get("barres", []):
        bar = LlmBar(**raw)
        armature = to_armature(bar)
        if armature is None:
            continue
        index, reason = _grounded_line(bar, texts, unparsed)
        if reason is None and _covered(armature, regex_bars + added):
            reason = "barre déjà lue"
        if reason is not None:
            rejected.append(reason)
            continue
        _apply_line_role(armature, bar, texts[index])
        added.append(armature)
    return added, rejected


def merge_reads(block: Block, llm: dict | None) -> dict:
    regex_bars = regex_read(block)
    out = {
        "armature": regex_bars,
        "confiance": 0.8 if regex_bars else 0.3,
        "methode": "regex",
        "llm_ajouts": 0,
        "llm_rejets": [],
    }
    if llm is None:
        return out
    added, rejected = _llm_additions(block, llm, regex_bars)
    out["llm_rejets"] = rejected
    if added:
        out.update(
            armature=regex_bars + added,
            methode="llm",
            llm_ajouts=len(added),
            confiance=out["confiance"] if regex_bars else 0.6,
            note=f"IA : {len(added)} barre(s) ajoutée(s) depuis une ligne non lue par regex",
        )
    return out


def _field(bars: list[Armature], name: str) -> list:
    if name == "espacement":
        return sorted(round(a.espacement_mm / 5.0) for a in bars if a.espacement_mm is not None)
    return sorted(str(getattr(a, name)) for a in bars if getattr(a, name) is not None)


def _dump(bars: list[Armature]) -> list[dict]:
    return [a.model_dump(exclude_none=True) for a in bars]


def _quality_row(block: Block, llm_read: dict, regex_bars: list[Armature], merged: dict) -> dict:
    return {
        "block_id": block.id,
        "fichier": block.page.fichier,
        "page": block.page.page,
        "bbox": block.bbox,
        "text": block.texts,
        "lignes_non_lues": unparsed_lines(block),
        "llm_parse": llm_read.get("raw"),
        "llm_ungrounded": llm_read.get("ungrounded", []),
        "regex_parse": _dump(regex_bars),
        "merged": _dump(merged["armature"]),
        "llm_ajouts": merged.get("llm_ajouts", 0),
        "llm_rejets": merged.get("llm_rejets", []),
        "confiance": merged["confiance"],
        "methode": merged["methode"],
    }


def _disagreement(block: Block, llm_bars: list[Armature], regex_bars: list[Armature], merged: dict) -> dict:
    return {
        "block_id": block.id,
        "page": f"{block.page.fichier} p{block.page.page}",
        "text": block.text,
        "llm": _dump(llm_bars),
        "regex": _dump(regex_bars),
        "retenu": _dump(merged["armature"]),
    }


def _quality_totals(scanned: list[Block], llm_reads: dict, reads: dict, stats: dict) -> dict:
    totals = {"regle_fusion": MERGE_RULE, "n_blocks_scanned": len(scanned)}
    totals.update({name: stats.get(key, default) for name, key, default in SCANNER_STATS})
    totals["n_blocks_ungrounded"] = sum(1 for b in scanned if llm_reads[b.id].get("ungrounded"))
    totals["n_blocs_enrichis"] = sum(1 for b in scanned if reads[b.id].get("llm_ajouts"))
    totals["n_barres_ajoutees"] = sum(reads[b.id].get("llm_ajouts", 0) for b in scanned)
    totals["n_barres_rejetees"] = sum(len(reads[b.id].get("llm_rejets", [])) for b in scanned)
    return totals


def llm_quality(blocks: list[Block], llm_reads: dict[str, dict], reads: dict[str, dict], stats: dict):
    scanned = [b for b in blocks if b.id in llm_reads]
    agree = dict.fromkeys(AGREEMENT_FIELDS, 0)
    examples, rows = [], []
    for block in scanned:
        llm_bars, regex_bars = llm_reads[block.id]["armature"], regex_read(block)
        same = {f: _field(llm_bars, f) == _field(regex_bars, f) for f in AGREEMENT_FIELDS}
        for name, equal in same.items():
            agree[name] += int(equal)
        rows.append(_quality_row(block, llm_reads[block.id], regex_bars, reads[block.id]))
        if not all(same.values()) and len(examples) < MAX_EXAMPLES:
            examples.append(_disagreement(block, llm_bars, regex_bars, reads[block.id]))
    quality = _quality_totals(scanned, llm_reads, reads, stats)
    quality["accord_llm_regex"] = {f: round(v / (len(scanned) or 1), 3) for f, v in agree.items()}
    quality["desaccords_exemples"] = examples
    return quality, rows
