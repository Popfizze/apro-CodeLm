from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import fitz

from . import REPO
from .ingest import plan_pdfs, shop_pdfs

RUN_OUTPUTS = [
    "items_plan",
    "items_atelier",
    "findings",
    "summary",
    "annexe_a_plan",
    "annexe_a_atelier",
    "report_pdf",
    "annotated_pdf",
    "llm_blocks",
]
MIN_TEXT_LAYER_CHARS = 20


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def _input_entry(pdf: Path, category: str | None = None) -> dict:
    with fitz.open(pdf) as doc:
        pages = doc.page_count
        with_text = sum(1 for page in doc if len(page.get_text("text").strip()) >= MIN_TEXT_LAYER_CHARS)
    entry = {"fichier": pdf.name, "chemin": _repo_relative(pdf)}
    if category is not None:
        entry["categorie"] = category
    entry.update(
        taille_octets=pdf.stat().st_size, sha256=_sha256(pdf), pages=pages, couche_texte=with_text * 2 > pages
    )
    return entry


def _outputs(out_dir: Path, written: dict[str, str]) -> dict[str, str | None]:
    return {
        k: (written[k] if k in written and (out_dir / written[k]).is_file() else None) for k in RUN_OUTPUTS
    }


def run_manifest(
    project_dir: Path,
    out_dir: Path,
    summary: dict,
    *,
    started: datetime,
    duree_s: float,
    gt: Path | None,
    model: str | None,
    written: dict[str, str],
) -> dict:
    project_dir, out_dir = Path(project_dir), Path(out_dir)
    mode = "ia_locale" if summary.get("llm_active") else "regex"
    evaluation = summary.get("evaluation")
    return {
        "run_id": f"{summary['projet']}-{started:%Y%m%dT%H%M%S}-{mode}",
        "projet": summary["projet"],
        "dossier": out_dir.name,
        "date": started.isoformat(timespec="seconds"),
        "mode": mode,
        "modele": model,
        "entrees": {
            "plan": [_input_entry(p) for p in plan_pdfs(project_dir)],
            "atelier": [_input_entry(p, p.parent.name) for p in shop_pdfs(project_dir)],
            "verite_terrain": {"fichier": Path(gt).name, "sha256": _sha256(Path(gt))} if gt else None,
        },
        "sorties": _outputs(out_dir, written),
        "etapes": summary.get("etapes", []),
        "duree_s": round(duree_s, 1),
        "totaux": summary["totaux"],
        "evaluation": {"rappel": evaluation["rappel"], "precision": evaluation["precision"]}
        if evaluation
        else None,
    }
