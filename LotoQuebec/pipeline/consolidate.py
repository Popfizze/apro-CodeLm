from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pipeline.jev.answers import answer_value
from pipeline.jev.contract import SUBJECTS
from pipeline.records import Answers, Passage

NATURE_RANK = {
    "approval": 9,
    "decision": 8,
    "validation": 7,
    "owner_change": 7,
    "payment": 6,
    "invoice": 6,
    "finding": 5,
    "risk": 5,
    "delivery": 4,
    "commitment": 3,
    "proposal": 2,
    "information": 1,
    "noise": 0,
}
KIND_RANK = {
    "adr": 6,
    "contract": 6,
    "project_doc": 5,
    "meeting": 4,
    "email": 3,
    "invoice": 3,
    "ticket": 2,
    "image": 2,
    "csv": 2,
    "teams": 1,
    "archive": 0,
    "event": 3,
}
STATEMENT_NATURES = frozenset(NATURE_RANK) - {"information", "noise"}
AUTHORITY_LABELS = ["bruit", "informel", "opérationnel", "formel/approuvé"]
SUPPORTING_LIMIT = 4
RULES = {
    "R1": "Énoncé courant = autorité la plus haute, puis date des faits la plus récente, "
    "parmi les énoncés non remplacés.",
    "R2": "Une proposition ne remplace jamais une décision ou une approbation.",
    "R3": "Un correctif annoncé (livraison) ne vaut pas validation : il ne remplace pas un constat, "
    "un risque ou une validation.",
    "R4": "Une contradiction se résout par l'autorité, puis par la date des faits.",
    "R5": "Un doublon (même contenu dans un autre fichier) n'est pas une confirmation indépendante.",
}
GUARDS = [
    ("R2", "proposal", ("decision", "approval")),
    ("R3", "delivery", ("finding", "risk", "validation")),
]


@dataclass
class Evidence:
    passages: list[Passage]
    decisions: dict[str, Answers]
    pairs: list[dict[str, Any]]
    by_id: dict[str, Passage] = field(init=False)
    superseded_by: dict[str, list[str]] = field(default_factory=dict)
    guarded: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.by_id = {passage["id"]: passage for passage in self.passages}

    def value(self, passage_id: str, key: str) -> Any:
        return answer_value(self.decisions[passage_id][key])

    def authority(self, passage: Passage) -> float:
        return float(self.value(passage["id"], "authority"))

    def nature(self, passage: Passage) -> str:
        return str(self.value(passage["id"], "nature"))


def is_true(answer: dict[str, Any]) -> bool:
    return float(answer["noul"]) >= 0.5


def guard_for(evidence: Evidence, pair: dict[str, Any]) -> str | None:
    older, newer = evidence.value(pair["a"], "nature"), evidence.value(pair["b"], "nature")
    for rule, newer_nature, older_natures in GUARDS:
        if newer == newer_nature and older in older_natures:
            return rule
    return None


def apply_supersessions(evidence: Evidence) -> None:
    for pair in evidence.pairs:
        if not is_true(pair["supersedes"]):
            continue
        rule = guard_for(evidence, pair)
        if rule:
            reference = {"a": pair["a"], "b": pair["b"], "subject": pair["subject"]}
            evidence.guarded.append({**reference, "rule": rule, "note": RULES[rule]})
        else:
            evidence.edges.append(pair)
            evidence.superseded_by.setdefault(pair["a"], []).append(pair["b"])


def statement_summary(evidence: Evidence, passage: Passage) -> dict[str, Any]:
    authority = round(evidence.authority(passage))
    fields = ("id", "source_id", "path", "locator", "date", "author", "kind", "text")
    return {
        **{name: passage[name] for name in fields},
        "nature": evidence.nature(passage),
        "authority": authority,
        "authority_label": AUTHORITY_LABELS[authority],
        "engine": evidence.decisions[passage["id"]]["subject"].get("engine"),
    }


def rank_key(evidence: Evidence, passage: Passage) -> tuple[Any, ...]:
    return (
        evidence.authority(passage),
        (passage["date"] or "")[:10],
        NATURE_RANK.get(evidence.nature(passage), 0),
        len(passage["text"]),
        KIND_RANK.get(passage["kind"], 0),
        passage["date"] or "",
    )


def is_subject_statement(evidence: Evidence, passage: Passage) -> bool:
    return (
        not passage["duplicate_of"]
        and evidence.nature(passage) in STATEMENT_NATURES
        and evidence.authority(passage) >= 1
    )


def current_pool(evidence: Evidence, statements: list[Passage]) -> list[Passage]:
    live = [passage for passage in statements if passage["id"] not in evidence.superseded_by]
    decided = [passage for passage in live if evidence.nature(passage) != "proposal"]
    return sorted(decided or live, key=lambda passage: rank_key(evidence, passage), reverse=True)


def supporting(evidence: Evidence, pool: list[Passage]) -> list[dict[str, Any]]:
    seen = {pool[0]["source_id"]} if pool else set()
    chosen: list[dict[str, Any]] = []
    for passage in pool[1:]:
        if passage["source_id"] not in seen and len(chosen) < SUPPORTING_LIMIT:
            chosen.append(statement_summary(evidence, passage))
            seen.add(passage["source_id"])
    return chosen


def replacement(evidence: Evidence, passage_id: str) -> dict[str, Any]:
    passage = evidence.by_id[passage_id]
    return {name: passage[name] for name in ("id", "date", "source_id", "locator")}


def history(evidence: Evidence, statements: list[Passage]) -> list[dict[str, Any]]:
    replaced = [passage for passage in statements if passage["id"] in evidence.superseded_by]
    return [
        {
            **statement_summary(evidence, passage),
            "superseded_by": [
                replacement(evidence, other) for other in evidence.superseded_by[passage["id"]]
            ],
        }
        for passage in sorted(replaced, key=lambda passage: passage["date"] or "")
    ]


def contradiction_reference(evidence: Evidence, passage: Passage) -> dict[str, Any]:
    return {
        "id": passage["id"],
        "source_id": passage["source_id"],
        "locator": passage["locator"],
        "date": passage["date"],
        "authority": evidence.authority(passage),
        "text": passage["text"][:300],
    }


def authority_text(evidence: Evidence, passage: Passage) -> str:
    authority = evidence.authority(passage)
    return f"{AUTHORITY_LABELS[round(authority)]} ({authority:g})"


def winner_by_rules(evidence: Evidence, first: Passage, second: Passage) -> tuple[Passage | None, str]:
    first_replaced = first["id"] in evidence.superseded_by
    second_replaced = second["id"] in evidence.superseded_by
    if first_replaced != second_replaced:
        loser = first if first_replaced else second
        replaced_by = ", ".join(evidence.superseded_by[loser["id"]])
        return (second if first_replaced else first), f"R1 : {loser['id']} remplacé par {replaced_by}"
    if evidence.authority(first) != evidence.authority(second):
        return max((first, second), key=evidence.authority), "R4"
    if (first["date"] or "") != (second["date"] or ""):
        return max((first, second), key=lambda passage: passage["date"] or ""), "R4"
    return None, "non résolu : même autorité et même date"


def rule_text(evidence: Evidence, winner: Passage, loser: Passage, reason: str) -> str:
    if evidence.authority(winner) > evidence.authority(loser):
        return f"{reason} ; autorité : {authority_text(evidence, winner)} > {authority_text(evidence, loser)}"
    if (winner["date"] or "") > (loser["date"] or ""):
        won, lost = (winner["date"] or "?")[:10], (loser["date"] or "?")[:10]
        return f"{reason} ; date des faits : {won} > {lost}"
    return f"{reason} ; {winner['id']} reste valide (non remplacé)"


def both_replaced_rule(evidence: Evidence, current_id: str | None) -> str:
    current = evidence.by_id.get(current_id or "")
    located = f" ({current['locator']})" if current else ""
    return f"R1 : les deux énoncés sont remplacés ; énoncé courant = {current_id}{located}"


def resolve(evidence: Evidence, pair: dict[str, Any], current_id: str | None) -> dict[str, Any]:
    first, second = evidence.by_id[pair["a"]], evidence.by_id[pair["b"]]
    winner, loser, rule = None, None, both_replaced_rule(evidence, current_id)
    if not (first["id"] in evidence.superseded_by and second["id"] in evidence.superseded_by):
        winner, rule = winner_by_rules(evidence, first, second)
        loser = (second if winner is first else first) if winner else None
        if winner and loser:
            rule = rule_text(evidence, winner, loser, rule)
    return {
        "a": contradiction_reference(evidence, first),
        "b": contradiction_reference(evidence, second),
        "subject": pair["subject"],
        "winner": winner["id"] if winner else current_id,
        "loser": loser["id"] if loser else None,
        "rule": rule,
        "b_supersedes_a": is_true(pair["supersedes"]),
    }


def counters(
    evidence: Evidence, passages: list[Passage], replaced: int, contradictions: int
) -> dict[str, Any]:
    originals = [passage for passage in passages if not passage["duplicate_of"]]

    def flagged(key: str) -> int:
        return sum(float(evidence.value(passage["id"], key)) >= 0.5 for passage in originals)

    return {
        "passages": len(passages),
        "independent_passages": len(originals),
        "sources": len({passage["source_id"] for passage in passages}),
        "by_nature": dict(Counter(evidence.nature(passage) for passage in originals)),
        "flags_risk": flagged("flags_risk"),
        "has_deadline": flagged("has_deadline"),
        "commitments_with_owner": flagged("is_commitment_with_owner"),
        "superseded": replaced,
        "contradictions": contradictions,
    }


def subject_passages(evidence: Evidence, subject: str) -> list[Passage]:
    decided = [passage for passage in evidence.passages if passage["id"] in evidence.decisions]
    return [passage for passage in decided if evidence.value(passage["id"], "subject") == subject]


def subject_contradictions(evidence: Evidence, subject: str, current_id: str | None) -> list[dict[str, Any]]:
    relevant = [pair for pair in evidence.pairs if subject in pair["subject"].split("|")]
    return [resolve(evidence, pair, current_id) for pair in relevant if is_true(pair["contradicts"])]


def subject_state(evidence: Evidence, subject: str) -> dict[str, Any]:
    passages = subject_passages(evidence, subject)
    statements = [passage for passage in passages if is_subject_statement(evidence, passage)]
    pool = current_pool(evidence, statements)
    current = statement_summary(evidence, pool[0]) if pool else None
    contradictions = subject_contradictions(evidence, subject, current["id"] if current else None)
    replaced = history(evidence, statements)
    return {
        "description": SUBJECTS[subject],
        "current": current,
        "supporting": supporting(evidence, pool),
        "history": replaced,
        "contradictions": contradictions,
        "counters": counters(evidence, passages, len(replaced), len(contradictions)),
    }


def global_counters(evidence: Evidence, noise: list[str]) -> dict[str, Any]:
    passages = evidence.passages
    return {
        "passages": len(passages),
        "sources": len({passage["source_id"] for passage in passages}),
        "duplicates": sum(1 for passage in passages if passage["duplicate_of"]),
        "passage_decisions": sum(len(answers) for answers in evidence.decisions.values()),
        "pairs": len(evidence.pairs),
        "contradictions": sum(is_true(pair["contradicts"]) for pair in evidence.pairs),
        "supersessions": len(evidence.edges),
        "supersessions_blocked_by_guards": len(evidence.guarded),
        "noise_passages": len(noise),
    }


def consolidate(passages: list[Passage], decided: dict[str, Any], version: str, as_of: str) -> dict[str, Any]:
    evidence = Evidence(passages, decided["passages"], decided["pairs"])
    apply_supersessions(evidence)
    subjects = {subject: subject_state(evidence, subject) for subject in SUBJECTS if subject != "noise"}
    noise = [
        passage["id"]
        for passage in passages
        if passage["id"] in evidence.decisions and evidence.value(passage["id"], "subject") == "noise"
    ]
    return {
        "version": version,
        "as_of": as_of,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "engine": decided["engine"],
        "rules": RULES,
        "subjects": subjects,
        "guards_applied": evidence.guarded,
        "noise_passages": noise,
        "counters": global_counters(evidence, noise),
    }


def summary(state: dict[str, Any]) -> str:
    totals = state["counters"]
    return (
        f"[state] {state['version']}: {len(state['subjects'])} subjects, "
        f"contradictions={totals['contradictions']}, supersessions={totals['supersessions']} "
        f"(blocked by guards: {totals['supersessions_blocked_by_guards']})"
    )
