import shutil
from collections.abc import Callable, Hashable
from pathlib import Path
from typing import Any

from pipeline.consolidate import consolidate
from pipeline.dedup import mark_duplicates
from pipeline.ingest import Ingester
from pipeline.jev.engines import JevEngine
from pipeline.jev.pairs import candidate_pairs
from pipeline.jev.run import classify_pairs, classify_passages
from pipeline.records import Passage, SourceRef
from pipeline.settings import AS_OF, EVENTS_DIR

EXTENSION_KINDS = {".eml": "email", ".pdf": "project_doc", ".xlsx": "project_doc"}
EVENT_VERSION = "v2-event"


def stage_event_file(event_path: Path) -> Path:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    target = EVENTS_DIR / event_path.name
    if event_path.resolve() != target.resolve():
        shutil.copy2(event_path, target)
    return target


def event_source(target: Path, kind: str | None) -> SourceRef:
    default_kind = EXTENSION_KINDS.get(target.suffix.lower(), "project_doc")
    return SourceRef(f"EVT-{target.stem}", f"events/{target.name}", kind or default_kind)


def ingest_event(event_path: Path, kind: str | None, ingester: Ingester) -> list[Passage]:
    target = stage_event_file(event_path)
    return ingester.ingest_file(target, event_source(target, kind))


def updated_decisions(
    engine: JevEngine, baseline: dict[str, Any], passages: list[Passage], new_ids: set[str]
) -> dict[str, Any]:
    decisions = classify_passages(engine, passages, baseline["passages"])
    known = {(pair["a"], pair["b"]) for pair in baseline["pairs"]}
    fresh = [
        pair for pair in candidate_pairs(passages, decisions) if (pair[0]["id"], pair[1]["id"]) not in known
    ]
    return {
        **baseline,
        "engine": engine.name,
        "model": engine.model,
        "passages": decisions,
        "pairs": list(baseline["pairs"]) + classify_pairs(engine, fresh),
        "event": {"passages": sorted(new_ids), "new_pairs": len(fresh)},
    }


def event_as_of(new_passages: list[Passage], as_of: str | None) -> str:
    return as_of or max((str(passage["date"]) for passage in new_passages if passage["date"]), default=AS_OF)


def run_event(
    event_path: Path,
    baseline: dict[str, Any],
    engine: JevEngine,
    ingester: Ingester,
    options: tuple[str | None, str | None] = (None, None),
) -> dict[str, Any]:
    as_of, kind = options
    new = ingest_event(event_path, kind, ingester)
    passages = baseline["passages"] + new
    mark_duplicates(passages)
    new_ids = {passage["id"] for passage in new}
    decided = updated_decisions(engine, baseline["decisions"], passages, new_ids)
    state = consolidate(passages, decided, EVENT_VERSION, event_as_of(new, as_of))
    state["event"] = {"file": new[0]["path"] if new else event_path.name, "passages": sorted(new_ids)}
    return {
        "passages": passages,
        "decisions": decided,
        "state": state,
        "diff": diff_states(baseline["state"], state, new_ids),
    }


def snapshot(current: dict[str, Any] | None) -> dict[str, Any] | None:
    if not current:
        return None
    return {key: current.get(key) for key in ("id", "locator", "date", "text")}


def counter_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    old = before.get("counters", {})
    return {
        key: value - old.get(key, 0) for key, value in after["counters"].items() if isinstance(value, int)
    }


def entries_not_in(
    entries: list[dict[str, Any]], known: set[Any], key: Callable[[dict[str, Any]], Hashable]
) -> list[dict[str, Any]]:
    return [entry for entry in entries if key(entry) not in known]


def shown_event_passages(after: dict[str, Any], new_ids: set[str]) -> list[str]:
    shown = {item.get("id") for item in [after.get("current") or {}, *after.get("supporting", [])]}
    return sorted(new_ids & shown)


def history_id(entry: dict[str, Any]) -> str:
    return str(entry["id"])


def pair_ids(entry: dict[str, Any]) -> tuple[str, str]:
    return entry["a"]["id"], entry["b"]["id"]


def subject_diff(before: dict[str, Any], after: dict[str, Any], new_ids: set[str]) -> dict[str, Any]:
    old_current, new_current = before.get("current") or {}, after.get("current") or {}
    old_history = {history_id(entry) for entry in before.get("history", [])}
    old_pairs = {pair_ids(entry) for entry in before.get("contradictions", [])}
    return {
        "current_changed": old_current.get("id") != new_current.get("id"),
        "current_v1": snapshot(old_current),
        "current_v2": snapshot(new_current),
        "newly_superseded": entries_not_in(after.get("history", []), old_history, history_id),
        "new_contradictions": entries_not_in(after.get("contradictions", []), old_pairs, pair_ids),
        "event_passages_in_subject": shown_event_passages(after, new_ids),
        "counters_delta": counter_delta(before, after),
    }


def has_changes(entry: dict[str, Any]) -> bool:
    changed = entry["current_changed"] or entry["newly_superseded"] or entry["new_contradictions"]
    return bool(changed or any(entry["counters_delta"].values()))


def diff_states(before: dict[str, Any], after: dict[str, Any], new_ids: set[str]) -> dict[str, Any]:
    subjects = {}
    for subject, state in after["subjects"].items():
        entry = subject_diff(before["subjects"].get(subject, {}), state, new_ids)
        if has_changes(entry):
            subjects[subject] = entry
    return {
        "from": before["version"],
        "to": after["version"],
        "as_of_from": before["as_of"],
        "as_of_to": after["as_of"],
        "event_passages": sorted(new_ids),
        "subjects": subjects,
    }
