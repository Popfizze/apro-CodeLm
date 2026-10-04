from __future__ import annotations

from pathlib import Path

from data_io import DELIVERABLES, dict_list, read_json

STATUSES = ["conforme", "non_conforme", "manquant_atelier", "ajoute_atelier"]
NO_SHEET = "—"


def _entry(rel: str, atelier: bool) -> dict:
    parts = Path(str(rel).replace("\\", "/")).parts
    item = {"fichier": parts[-1] if parts else str(rel)}
    if atelier:
        item["categorie"] = parts[-2] if len(parts) >= 2 and parts[-2].upper() != "DA" else None
    return item


def entries_from_summary(docs: dict) -> dict:
    return {
        "plan": [_entry(p, False) for p in docs.get("plan") or []],
        "atelier": [_entry(p, True) for p in docs.get("atelier") or []],
    }


def _dict_or(value, default):
    return value if isinstance(value, dict) else default


def _manifest_from_summary(summary: dict) -> dict:
    evaluation = _dict_or(summary.get("evaluation"), None)
    local_model = bool(summary.get("llm_active"))
    run = {
        "run_id": None,
        "date": summary.get("genere_le"),
        "mode": "ia_locale" if local_model else "regex",
        "modele": _dict_or(summary.get("llm"), {}).get("modele") if local_model else None,
        "entrees": entries_from_summary(summary.get("documents") or {}),
        "duree_s": None,
        "manifeste": False,
    }
    if evaluation and evaluation.get("verite_terrain"):
        run["entrees"]["verite_terrain"] = {"fichier": Path(str(evaluation["verite_terrain"])).name}
    return run


def load_manifest(res_dir: Path, summary: dict) -> dict:
    stored = read_json(res_dir / "run.json", None)
    run = {**stored, "manifeste": True} if isinstance(stored, dict) else _manifest_from_summary(summary)
    run["dossier"] = res_dir.name
    run.setdefault("projet", summary.get("projet") or res_dir.name)
    entrees = _dict_or(run.get("entrees"), {})
    entrees["plan"] = dict_list(entrees.get("plan"))
    entrees["atelier"] = dict_list(entrees.get("atelier"))
    entrees.setdefault("verite_terrain", None)
    run["entrees"] = entrees
    return run


def _totals(findings: list[dict]) -> dict:
    totals = dict.fromkeys(STATUSES, 0)
    for finding in findings:
        if finding.get("statut") in totals:
            totals[finding["statut"]] += 1
    return totals


def _sheet_rows(findings: list[dict]) -> list[dict]:
    sheets: dict[str, dict] = {}
    for finding in findings:
        key = finding.get("feuillet") or NO_SHEET
        row = sheets.setdefault(
            key,
            {
                "feuillet": key,
                "titre": "",
                "type_element": finding.get("type_element"),
                **dict.fromkeys(STATUSES, 0),
            },
        )
        if finding.get("statut") in STATUSES:
            row[finding["statut"]] += 1
    return sorted(sheets.values(), key=lambda r: str(r["feuillet"]))


def ensure_summary(name: str, summary: dict, findings: list[dict]) -> dict:
    summary = dict(summary) if isinstance(summary, dict) else {}
    summary.setdefault("projet", name)
    for key in DELIVERABLES:
        summary.pop(key, None)
    if not isinstance(summary.get("totaux"), dict):
        summary["totaux"] = _totals(findings)
    if not isinstance(summary.get("par_feuillet"), list):
        summary["par_feuillet"] = _sheet_rows(findings)
    return summary
