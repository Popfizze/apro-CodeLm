import time
from datetime import UTC, datetime
from typing import Any

from pipeline.jev.contract import PAIR_QUESTIONS, PASSAGE_QUESTIONS, pair_state, passage_state
from pipeline.jev.engines import JevEngine
from pipeline.jev.pairs import Decisions, Pair, candidate_pairs
from pipeline.records import Passage

PROGRESS_EVERY = 25


class Progress:
    def __init__(self, label: str, total: int) -> None:
        self.label, self.total, self.start = label, total, time.monotonic()

    def tick(self, done: int) -> None:
        if done % PROGRESS_EVERY == 0 or done == self.total:
            elapsed = time.monotonic() - self.start
            print(f"[jev] {self.label} {done}/{self.total} ({elapsed:.0f}s)", flush=True)


def canonical_root(passage: Passage, by_id: dict[str, Passage]) -> str:
    root = passage["duplicate_of"]
    while by_id[root]["duplicate_of"]:
        root = by_id[root]["duplicate_of"]
    return str(root)


def inherit_duplicates(passages: list[Passage], decisions: Decisions) -> None:
    by_id = {passage["id"]: passage for passage in passages}
    for passage in passages:
        if passage["duplicate_of"]:
            root = canonical_root(passage, by_id)
            decisions[passage["id"]] = {
                key: {**answer, "inherited_from": root} for key, answer in decisions[root].items()
            }


def classify_passages(
    engine: JevEngine, passages: list[Passage], known: Decisions | None = None
) -> Decisions:
    decisions: Decisions = {
        key: value for key, value in (known or {}).items() if "inherited_from" not in value
    }
    pending = [
        passage for passage in passages if not passage["duplicate_of"] and passage["id"] not in decisions
    ]
    progress = Progress("passages", len(pending))
    for done, passage in enumerate(pending, start=1):
        decisions[passage["id"]] = engine.ask(passage_state(passage), PASSAGE_QUESTIONS)
        progress.tick(done)
    inherit_duplicates(passages, decisions)
    return decisions


def classify_pairs(engine: JevEngine, candidates: list[Pair]) -> list[dict[str, Any]]:
    progress = Progress("pairs", len(candidates))
    results = []
    for done, (first, second, subject) in enumerate(candidates, start=1):
        answers = engine.ask(pair_state(first, second), PAIR_QUESTIONS)
        results.append(
            {
                "a": first["id"],
                "b": second["id"],
                "subject": subject,
                "contradicts": answers["contradicts"],
                "supersedes": answers["supersedes"],
            }
        )
        progress.tick(done)
    return results


def run_jev(engine: JevEngine, passages: list[Passage], known: Decisions | None = None) -> dict[str, Any]:
    decisions = classify_passages(engine, passages, known)
    pairs = classify_pairs(engine, candidate_pairs(passages, decisions))
    return {
        "engine": engine.name,
        "model": engine.model,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "questions": {"passage": PASSAGE_QUESTIONS, "pair": PAIR_QUESTIONS},
        "passages": decisions,
        "pairs": pairs,
    }


def is_true(answer: dict[str, Any]) -> bool:
    return float(answer["noul"]) >= 0.5


def summary(result: dict[str, Any]) -> str:
    pairs = result["pairs"]
    contradictions = sum(is_true(pair["contradicts"]) for pair in pairs)
    supersessions = sum(is_true(pair["supersedes"]) for pair in pairs)
    return (
        f"[jev] engine={result['engine']} passages={len(result['passages'])} pairs={len(pairs)} "
        f"contradicts={contradictions} supersedes={supersessions}"
    )
