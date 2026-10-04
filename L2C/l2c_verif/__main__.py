from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import REPO
from .ingest import plan_pdfs
from .llm import DEFAULT_MODEL
from .pipeline import run_project

GROUND_TRUTH_PATTERN = "*dismatch*.xlsx"


def _split(value: str | None) -> list[str] | None:
    return [s.strip() for s in value.split(",") if s.strip()] if value else None


def _add_llm_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--llm", action="store_true", help="enable the local Ollama base scan (off by default)"
    )
    parser.add_argument(
        "--llm-sheets", help="restrict the LLM scan to these plan sheets (shop drawings always scanned)"
    )
    parser.add_argument(
        "--llm-types",
        default="fondation,colonne",
        help="element types sent to the LLM (extractors that consume block readings)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="blocks per LLM request (small batches avoid cross-block contamination)",
    )
    parser.add_argument(
        "--llm-refresh",
        action="store_true",
        help="query the model again instead of reading cache/llm (cache rewritten)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="l2c_verif")
    commands = parser.add_subparsers(dest="cmd", required=True)
    run = commands.add_parser("run")
    run.add_argument("--project", required=True, type=Path)
    run.add_argument("--out", type=Path)
    run.add_argument("--gt", type=Path)
    run.add_argument("--pages", help="restrict plan sheets, e.g. S-100,S-200")
    run_all = commands.add_parser("run-all")
    run_all.add_argument("--data", type=Path, default=REPO / "data")
    run_all.add_argument("--results", type=Path, default=REPO / "results")
    for command in (run, run_all):
        _add_llm_options(command)
    return parser


def _print_summary(summary: dict) -> None:
    print(f"[{summary['projet']}] totaux={summary['totaux']}")
    evaluation = summary.get("evaluation")
    if not evaluation:
        return
    print(
        f"[{summary['projet']}] rappel={evaluation['rappel']} precision={evaluation['precision']} "
        f"hors_verite_terrain={evaluation['hors_verite_terrain']}"
    )
    for d in evaluation["details"]:
        print(
            f"   {d['feuillet']:7} {d['localisation'][:24]:24} "
            f"attendu={d['ecart_attendu']!s:5} trouve={d['trouve']!s:5} "
            f"{d['statut'] or '-':16} {d['finding_id'] or ''}"
        )


def _projects(data_root: Path) -> list[Path]:
    return sorted(p for p in data_root.iterdir() if p.is_dir() and plan_pdfs(p))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    options = {
        "use_llm": args.llm,
        "llm_sheets": _split(args.llm_sheets),
        "llm_types": _split(args.llm_types),
        "model": args.model,
        "batch_size": args.batch_size,
        "llm_refresh": args.llm_refresh,
    }
    if args.cmd == "run":
        out = args.out or REPO / "results" / args.project.name
        _print_summary(run_project(args.project, out, gt=args.gt, sheets=_split(args.pages), **options))
        return 0
    for project in _projects(args.data):
        ground_truth = next(iter(project.glob(GROUND_TRUTH_PATTERN)), None)
        _print_summary(run_project(project, args.results / project.name, gt=ground_truth, **options))
    return 0


if __name__ == "__main__":
    sys.exit(main())
