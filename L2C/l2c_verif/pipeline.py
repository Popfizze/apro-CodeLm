from __future__ import annotations

import json
import logging
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import CACHE_DIR
from . import extract as extractors
from .annex_a import export_annex_a
from .annotate import build_annotated_pdfs
from .blocks import Block, segment_page
from .evaluate import evaluate
from .grid import detect_grid
from .ingest import PageRef, index_project
from .llm import DEFAULT_MODEL, LlmScanner, ollama_available, unload_model
from .manifest import run_manifest
from .match import GridPositions, level_key, match_and_compare
from .models import Finding, Item
from .readers import llm_quality, merge_reads, needs_llm, unparsed_lines
from .report import build_report
from .style import STATUSES

log = logging.getLogger("l2c_verif")


@dataclass
class LlmOptions:
    enabled: bool
    sheets: list[str] | None
    types: list[str] | None
    model: str
    batch_size: int
    cache_dir: Path
    refresh: bool

    def in_scope(self, block: Block) -> bool:
        page = block.page
        if self.sheets and page.source != "atelier" and page.feuillet not in self.sheets:
            return False
        if self.types and page.type_element not in self.types:
            return False
        return needs_llm(block)


class Stages:
    def __init__(self):
        self.rows: list[dict] = []

    @contextmanager
    def stage(self, name: str):
        started = time.time()
        record = {"nom": name, "duree_s": 0.0, "n": 0}
        self.rows.append(record)
        try:
            yield record
        finally:
            record["duree_s"] = round(time.time() - started, 2)
            log.info("stage %-14s %7.2fs n=%s", name, record["duree_s"], record["n"])


def _dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _index(project_dir: Path, sheets: list[str] | None, stages: Stages) -> list[PageRef]:
    with stages.stage("indexation") as record:
        pages = index_project(project_dir)
        if sheets:
            pages = [p for p in pages if p.source == "atelier" or p.feuillet in sheets]
        record["n"] = len(pages)
    return pages


def _detect_grids(pages: list[PageRef], types: set[str], stages: Stages) -> dict:
    with stages.stage("grille") as record:
        grids = {p.key: detect_grid(p.lines, p.width, p.height) for p in pages if p.type_element in types}
        record["n"] = sum(1 for g in grids.values() if g.ok)
    return grids


def _segment(pages: list[PageRef], types: set[str], stages: Stages) -> dict[str, list[Block]]:
    with stages.stage("blocs") as record:
        blocks = {p.key: segment_page(p) for p in pages if p.type_element in types}
        record["n"] = sum(len(v) for v in blocks.values())
    return blocks


def _scan(blocks: list[Block], options: LlmOptions, info: dict, record: dict) -> tuple[dict, LlmScanner]:
    scope = [b for b in blocks if options.in_scope(b)]
    scanner = LlmScanner(
        options.cache_dir, model=options.model, batch_size=options.batch_size, refresh=options.refresh
    )
    reads = scanner.scan(scope, line_filter=unparsed_lines)
    unload_model(options.model)
    info.update(active=True, blocs_envoyes=len(scope), **scanner.stats)
    if scanner.batch_seconds:
        info["s_par_lot"] = round(sum(scanner.batch_seconds) / len(scanner.batch_seconds), 1)
        info["s_par_lot_premiers"] = scanner.batch_seconds[:5]
    record["n"] = len(reads)
    return reads, scanner


def _scan_llm(
    blocks: list[Block], options: LlmOptions, info: dict, stages: Stages
) -> tuple[dict, LlmScanner | None]:
    with stages.stage("scan_llm") as record:
        if options.enabled and ollama_available():
            return _scan(blocks, options, info, record)
        if options.enabled:
            log.warning("Ollama not reachable: regex fallback")
            info["note"] = "Ollama indisponible, repli regex"
    return {}, None


def _read_blocks(blocks: list[Block], llm_reads: dict, info: dict, stages: Stages) -> dict[str, dict]:
    with stages.stage("lecture") as record:
        reads = {b.id: merge_reads(b, llm_reads.get(b.id)) for b in blocks}
        if llm_reads:
            info["blocs_enrichis"] = sum(1 for b in blocks if reads[b.id].get("llm_ajouts"))
            info["barres_ajoutees"] = sum(reads[b.id].get("llm_ajouts", 0) for b in blocks)
        record["n"] = len(reads)
    return reads


def _extract(ctx: extractors.Ctx, stages: Stages) -> tuple[list[Item], list[Item]]:
    with stages.stage("extraction") as record:
        plan_items, shop_items = extractors.run_all(ctx)
        record["n"] = len(plan_items) + len(shop_items)
    return plan_items, shop_items


def _compare(project: str, plan_items: list[Item], shop_items: list[Item], grids: dict, stages: Stages):
    with stages.stage("comparaison") as record:
        covered = {level_key(i) for i in shop_items}
        in_scope = [i for i in plan_items if level_key(i) in covered]
        out_of_scope = Counter(i.feuillet for i in plan_items if level_key(i) not in covered)
        findings = match_and_compare(project, in_scope, shop_items, position=GridPositions(plan_items, grids))
        record["n"] = len(findings)
    return findings, out_of_scope


def _evaluate(findings: list[Finding], gt: Path | None, stages: Stages) -> dict | None:
    if not gt:
        return None
    with stages.stage("evaluation") as record:
        evaluation = evaluate(findings, Path(gt))
        record["n"] = len(evaluation["details"])
    return evaluation


def _sheet_rows(
    pages: list[PageRef], findings: list[Finding], types: set[str], out_of_scope: Counter
) -> list[dict]:
    by_sheet: dict[str, Counter] = {}
    for f in findings:
        by_sheet.setdefault(f.feuillet, Counter())[f.statut] += 1
    rows = []
    for page in pages:
        if page.source != "plan" or not page.feuillet:
            continue
        counts = by_sheet.get(page.feuillet, Counter())
        rows.append(
            {
                "feuillet": page.feuillet,
                "titre": page.titre,
                "type_element": page.type_element,
                "page": page.page,
                **{s: counts.get(s, 0) for s in STATUSES},
                "couvert": page.type_element in types,
                "hors_portee_atelier": out_of_scope.get(page.feuillet, 0),
            }
        )
    return rows


def _summary(
    project: str, pages: list[PageRef], findings: list[Finding], rows: list[dict], types: set[str]
) -> dict:
    totals = Counter(f.statut for f in findings)
    return {
        "projet": project,
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "documents": {
            "plan": sorted({p.fichier for p in pages if p.source == "plan"}),
            "atelier": sorted({p.fichier for p in pages if p.source == "atelier"}),
        },
        "par_feuillet": rows,
        "totaux": {s: totals.get(s, 0) for s in STATUSES},
        "types_couverts": sorted(types),
    }


def _write_outputs(
    out_dir: Path, items: tuple[list[Item], list[Item]], findings: list[Finding], summary: dict
) -> dict:
    plan_items, shop_items = items
    _dump(out_dir / "items_plan.json", [i.model_dump() for i in plan_items])
    _dump(out_dir / "items_atelier.json", [i.model_dump() for i in shop_items])
    _dump(out_dir / "findings.json", [f.model_dump(exclude_none=True) for f in findings])
    _dump(out_dir / "summary.json", summary)
    return {
        "items_plan": "items_plan.json",
        "items_atelier": "items_atelier.json",
        "findings": "findings.json",
        "summary": "summary.json",
    }


def _try_build(label: str, build) -> bool:
    try:
        build()
    except Exception as exc:
        log.warning("%s not built: %s", label, exc)
        return False
    return True


def _post_outputs(out_dir: Path, project_dir: Path, summary: dict) -> dict[str, str]:
    written: dict[str, str] = {}
    if _try_build("report.pdf", lambda: build_report(out_dir)):
        summary["report_pdf"] = written["report_pdf"] = "report.pdf"
    if _try_build("annotated PDFs", lambda: build_annotated_pdfs(out_dir, project_dir)):
        summary["annotated_pdf"] = written["annotated_pdf"] = "annotated.pdf"
    if _try_build("Annex A export", lambda: export_annex_a(out_dir)):
        written.update(annexe_a_plan="annexe_a_plan.json", annexe_a_atelier="annexe_a_atelier.json")
    if "report_pdf" in written or "annotated_pdf" in written:
        _dump(out_dir / "summary.json", summary)
    return written


def run_project(
    project_dir: Path,
    out_dir: Path,
    gt: Path | None = None,
    use_llm: bool = True,
    sheets: list[str] | None = None,
    llm_sheets: list[str] | None = None,
    llm_types: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    batch_size: int = 5,
    cache_dir: Path | None = None,
    llm_refresh: bool = False,
) -> dict:
    project_dir, out_dir = Path(project_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    options = LlmOptions(
        use_llm, llm_sheets, llm_types, model, batch_size, cache_dir or CACHE_DIR / "llm", llm_refresh
    )
    stages, started = Stages(), datetime.now()
    pages = _index(project_dir, sheets, stages)
    types = extractors.implemented_types()
    grids, blocks = _detect_grids(pages, types, stages), _segment(pages, types, stages)
    all_blocks = [b for page_blocks in blocks.values() for b in page_blocks]
    llm_info = {"modele": model, "active": False}
    llm_reads, scanner = _scan_llm(all_blocks, options, llm_info, stages)
    reads = _read_blocks(all_blocks, llm_reads, llm_info, stages)
    quality = llm_quality(all_blocks, llm_reads, reads, scanner.stats) if scanner is not None else None
    ctx = extractors.Ctx(project=project_dir.name, pages=pages, blocks=blocks, reads=reads, grids=grids)
    plan_items, shop_items = _extract(ctx, stages)
    findings, out_of_scope = _compare(project_dir.name, plan_items, shop_items, grids, stages)
    evaluation = _evaluate(findings, gt, stages)
    summary = _summary(
        project_dir.name, pages, findings, _sheet_rows(pages, findings, types, out_of_scope), types
    )
    summary.update(llm_active=bool(llm_info.get("active")), llm=llm_info, etapes=stages.rows)
    if evaluation is not None:
        summary["evaluation"] = evaluation
    if quality is not None:
        summary["llm_qualite"] = quality[0]
        _dump(out_dir / "llm_blocks.json", quality[1])
    written = _write_outputs(out_dir, (plan_items, shop_items), findings, summary)
    if quality is not None:
        written["llm_blocks"] = "llm_blocks.json"
    written.update(_post_outputs(out_dir, project_dir, summary))
    manifest = run_manifest(
        project_dir,
        out_dir,
        summary,
        started=started,
        duree_s=(datetime.now() - started).total_seconds(),
        gt=gt,
        model=model if summary["llm_active"] else None,
        written=written,
    )
    _dump(out_dir / "run.json", manifest)
    return summary
