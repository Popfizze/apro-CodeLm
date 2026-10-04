from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from crop_images import CropBuilder, ItemCropBuilder, build_finding_crops
from data_io import (
    APP_DIR,
    ROOT,
    PdfIndex,
    copy_deliverables,
    dict_list,
    log,
    read_json,
    safe_stem,
    source_roots,
)
from manifests import ensure_summary, load_manifest
from page_images import build_doc_pages, build_run_pages

RESULT_FILES = ("summary.json", "findings.json")


def _run_entry(res_dir: Path, out_dir: Path) -> dict:
    dossier = res_dir.name
    findings = dict_list(read_json(res_dir / "findings.json", []))
    items_plan = dict_list(read_json(res_dir / "items_plan.json", []))
    items_atelier = dict_list(read_json(res_dir / "items_atelier.json", []))
    summary = ensure_summary(dossier, read_json(res_dir / "summary.json", {}), findings)
    run = load_manifest(res_dir, summary)
    origin = "" if run["manifeste"] else ", sans run.json"
    log(
        f"- {dossier} (projet {run.get('projet') or dossier}, {run.get('mode')}{origin}): "
        f"{len(findings)} findings, {len(items_plan)} plan items, {len(items_atelier)} atelier items"
    )
    paths = copy_deliverables(res_dir, run, out_dir / "reports" / safe_stem(dossier))
    log(f"  deliverables: {', '.join(k for k, v in paths.items() if v) or 'none found'}")
    return {
        "run": run,
        "summary": summary,
        "findings": findings,
        "items_plan": items_plan,
        "items_atelier": items_atelier,
        **paths,
        "pages_rapport": [],
        "pages_annote": [],
        "plans": [],
        "ateliers": [],
    }


def _item_crops(entry: dict, index: PdfIndex, item_crops: ItemCropBuilder) -> None:
    before = dict(item_crops.stats)
    for item in entry["items_plan"] + entry["items_atelier"]:
        item_crops.build(index, item)
    item_crops.save()
    log("  item crops: " + str({k: item_crops.stats[k] - before[k] for k in before}))


def _page_images(entry: dict, res_dir: Path, index: PdfIndex, out_dir: Path, force: bool) -> None:
    run = entry["run"]
    entry.update(build_run_pages(res_dir, run, out_dir, force))
    entry["plans"] = build_doc_pages(run, index, out_dir, force, "plan")
    entry["ateliers"] = build_doc_pages(run, index, out_dir, force, "atelier")
    shop_pages = sum(p["pages"] for p in entry["ateliers"])
    log(
        f"  pages: rapport {len(entry['pages_rapport'])}, annoté {len(entry['pages_annote'])}, "
        f"plans {[p['pages'] for p in entry['plans']]}, "
        f"dessins d'atelier {shop_pages} pages / {len(entry['ateliers'])} fichiers"
    )


def _render(entry: dict, res_dir: Path, data_root: Path, opts: argparse.Namespace, item_crops) -> None:
    run, dossier = entry["run"], res_dir.name
    index = PdfIndex(source_roots(data_root, str(run.get("projet") or dossier), dossier, run))
    try:
        stem = safe_stem(dossier)
        crops = CropBuilder(opts.out / "crops" / stem, f"crops/{stem}", opts.force)
        items = entry["items_plan"] + entry["items_atelier"]
        build_finding_crops(entry["findings"], items, res_dir, index, crops, opts.max_conforme)
        if item_crops is not None:
            _item_crops(entry, index, item_crops)
        if not opts.no_pages:
            _page_images(entry, res_dir, index, opts.out, opts.force)
    finally:
        index.close()


def build_run(
    res_dir: Path, data_root: Path, opts: argparse.Namespace, item_crops: ItemCropBuilder | None
) -> dict:
    entry = _run_entry(res_dir, opts.out)
    if not opts.no_crops:
        _render(entry, res_dir, data_root, opts, item_crops)
    return entry


def _run_order(entry: dict) -> tuple:
    run = entry.get("run", {})
    return (
        str(run.get("projet") or "").casefold(),
        str(run.get("date") or ""),
        str(run.get("dossier") or ""),
    )


def build_projects(runs: list[dict]) -> list[dict]:
    by_project: dict[str, list[dict]] = {}
    for entry in runs:
        run = entry["run"]
        by_project.setdefault(str(run.get("projet") or run.get("dossier")), []).append(run)
    projects = []
    for project in sorted(by_project, key=str.casefold):
        ordered = sorted(by_project[project], key=lambda r: (str(r.get("date") or ""), str(r.get("dossier"))))
        projects.append(
            {
                "projet": project,
                "runs": [r["dossier"] for r in ordered],
                "dernier_run": ordered[-1]["dossier"],
            }
        )
    return projects


def load_existing_runs(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    start, end = text.find("{"), text.rfind("}")
    try:
        runs = json.loads(text[start : end + 1]).get("runs", [])
    except ValueError:
        return []
    return [r for r in runs if isinstance(r, dict) and isinstance(r.get("run"), dict)]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build app/app_data.js, crops, page images and reports from results/."
    )
    parser.add_argument("--results", type=Path, default=ROOT / "results", help="pipeline results directory")
    parser.add_argument("--data", type=Path, default=ROOT / "data", help="source PDFs root (data/<PROJECT>/)")
    parser.add_argument("--out", type=Path, default=APP_DIR, help="app directory to write into")
    parser.add_argument("--project", action="append", help="only rebuild these results folder(s)")
    parser.add_argument("--no-crops", action="store_true", help="skip every image rendering step")
    parser.add_argument("--no-item-crops", action="store_true", help="skip the per-element crops")
    parser.add_argument(
        "--no-pages", action="store_true", help="skip the report, annotated and plan page images"
    )
    parser.add_argument("--force", action="store_true", help="re-render every image")
    parser.add_argument("--max-conforme", type=int, default=40, help="max conforme finding crops per run")
    return parser


def _result_dirs(results: Path, projects: list[str] | None) -> list[Path]:
    dirs = [d for d in results.iterdir() if d.is_dir() and any((d / name).is_file() for name in RESULT_FILES)]
    if projects:
        wanted = {p.casefold() for p in projects}
        dirs = [d for d in dirs if d.name.casefold() in wanted]
    return sorted(dirs, key=lambda p: p.name.casefold())


def _write_bundle(out_dir: Path, runs: list[dict]) -> None:
    bundle = {"projets": build_projects(runs), "runs": runs}
    payload = "window.APP_DATA = " + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + ";\n"
    target = out_dir / "app_data.js"
    tmp = target.with_suffix(".js.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, target)
    size = len(payload) / 1e6
    log(f"wrote {target} ({size:.1f} MB, {len(runs)} run(s), {len(bundle['projets'])} project(s))")


def main(argv: list[str] | None = None) -> int:
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(errors="replace")
    args = _parser().parse_args(argv)
    if not args.results.is_dir():
        log(f"No results directory at {args.results}: nothing to build.")
        return 1
    dirs = _result_dirs(args.results, args.project)
    if not dirs:
        log(f"No run results found in {args.results}.")
        return 1
    with_item_crops = not args.no_crops and not args.no_item_crops
    item_crops = ItemCropBuilder(args.out / "crops" / "items", args.force) if with_item_crops else None
    runs = [build_run(d, args.data, args, item_crops) for d in dirs]
    if args.project:
        names = {r["run"]["dossier"] for r in runs}
        previous = [
            r for r in load_existing_runs(args.out / "app_data.js") if r["run"].get("dossier") not in names
        ]
        runs = previous + runs
    runs.sort(key=_run_order)
    _write_bundle(args.out, runs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
