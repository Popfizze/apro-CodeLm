import argparse
import sys
from pathlib import Path
from typing import Any

from pipeline.consolidate import consolidate
from pipeline.consolidate import summary as state_summary
from pipeline.corpus import CorpusError, check_corpus
from pipeline.embeddings import embedding_index
from pipeline.event import run_event
from pipeline.evidence import EvidenceError
from pipeline.ingest import Ingester, ingest_corpus
from pipeline.jev.engines import select_engine
from pipeline.jev.run import run_jev
from pipeline.jev.run import summary as jev_summary
from pipeline.jsonio import write_json, write_jsonl
from pipeline.knowledge import build_knowledge, load_content
from pipeline.ollama import OllamaUnavailableError
from pipeline.records import Passage
from pipeline.settings import AS_OF, OUT
from pipeline.sources import source_registry

BASELINE = "v1-baseline"


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m pipeline", description="Build the NOVA project memory.")
    parser.add_argument(
        "--event", type=Path, help="new information file: writes the v2 snapshot and the diff"
    )
    parser.add_argument("--as-of", help="as_of timestamp of the v2 snapshot (default: latest event date)")
    parser.add_argument("--kind", help="passage kind of the event file (default: from its extension)")
    parser.add_argument("--skip-embeddings", action="store_true", help="do not compute passage embeddings")
    return parser.parse_args(argv)


def write_embeddings(passages: list[Passage], name: str) -> None:
    try:
        index = embedding_index(passages)
    except OllamaUnavailableError as error:
        print(f"[embed] skipped, the app falls back to BM25: {error}")
        return
    write_json(OUT / name, index)
    print(
        f"[embed] {index['count']} vectors, model={index['model']}, dimension={index['dimension']} -> {name}"
    )


def build_baseline(ingester: Ingester) -> dict[str, Any]:
    files = check_corpus()
    passages = ingest_corpus(files, ingester)
    registry = source_registry(files, passages)
    write_jsonl(OUT / "passages.jsonl", passages)
    write_json(OUT / "sources.json", registry)
    print(f"[ingest] {len(files)} project sources -> {len(passages)} passages")
    engine = select_engine()
    decided = run_jev(engine, passages)
    write_json(OUT / "jev_decisions.json", decided)
    print(jev_summary(decided))
    state = consolidate(passages, decided, BASELINE, AS_OF)
    write_json(OUT / "state.json", state)
    print(state_summary(state))
    knowledge = build_knowledge(load_content(), passages, registry, BASELINE)
    write_json(OUT / "kb.json", knowledge)
    print(f"[evidence] {knowledge['meta']['nb_citations_verifiees']} citations verified, 0 discrepancies")
    return {"passages": passages, "decisions": decided, "state": state, "engine": engine}


def build_event(arguments: argparse.Namespace, baseline: dict[str, Any], ingester: Ingester) -> None:
    result = run_event(
        arguments.event, baseline, baseline["engine"], ingester, (arguments.as_of, arguments.kind)
    )
    write_jsonl(OUT / "passages_v2.jsonl", result["passages"])
    write_json(OUT / "jev_decisions_v2.json", result["decisions"])
    write_json(OUT / "state_v2.json", result["state"])
    write_json(OUT / "diff_v1_v2.json", result["diff"])
    changed = [name for name, entry in result["diff"]["subjects"].items() if entry["current_changed"]]
    print(f"{state_summary(result['state'])}; changed subjects: {changed}")
    if not arguments.skip_embeddings:
        write_embeddings(result["passages"], "embeddings_v2.json")


def run(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    ingester = Ingester()
    try:
        baseline = build_baseline(ingester)
        if not arguments.skip_embeddings:
            write_embeddings(baseline["passages"], "embeddings.json")
        if arguments.event:
            build_event(arguments, baseline, ingester)
    except (CorpusError, EvidenceError, OllamaUnavailableError) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    return 0
