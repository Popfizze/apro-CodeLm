import re
from collections import defaultdict

from pipeline.dates import days_between
from pipeline.jev.answers import answer_value
from pipeline.records import Answers, Passage

NATURE_RANK = {
    "approval": 9,
    "decision": 8,
    "validation": 7,
    "owner_change": 7,
    "payment": 6,
    "invoice": 6,
    "proposal": 5,
    "delivery": 5,
    "risk": 4,
    "finding": 4,
    "commitment": 3,
}
ENTITY_PATTERNS = [
    (r"\b(?:acc|sec|int|data|ops|perf)-\d{3}\b", None),
    (r"\b(?:cr|inv)-\d{2,3}\b", None),
    (r"\b(\d{1,2})\s+oct(?:obre)?\b", "slot:october_date"),
    (r"\b2026-10-(\d{2})\b", "slot:october_date"),
    (r"\b(?:le|au|du)\s+\**(15|22)\b(?!\s*\d)", "slot:october_date"),
    (r"\b(\d{1,3})\s000\s?\$", "slot:amount"),
    (r"canada central|east us|canada", "region"),
    (r"rollback|retour arrière|runbook", "runbook"),
    (r"chargée? de projet|reprend|élodie|nicolas", "owner"),
    (r"sécurité|audit|journalisation", "topic:security"),
    (r"accessibilit|clavier|contraste|label", "topic:accessibility"),
    (r"connecteur", "topic:integration"),
    (r"doublon|idempotence", "topic:data"),
    (r"budget|plafond|montant", "topic:budget"),
    (r"mobile", "topic:mobile"),
    (r"exploitation", "runbook"),
]
STATUS_TOPICS = {
    "topic:security": "security",
    "topic:accessibility": "accessibility",
    "runbook": "operations_runbook",
    "topic:budget": "vendor_contract",
    "slot:october_date": "go_live_date",
}
STATUS_SUBJECT = "status_reporting"
STATUS_WINDOW_DAYS = 21
CHANGE_REFERENCE = re.compile(r"(cr|inv)-")
MIN_STATEMENT_LENGTH = 25

Pair = tuple[Passage, Passage, str]
Decisions = dict[str, Answers]


def value(answers: Answers, key: str) -> object:
    return answer_value(answers[key])


def entities(text: str, subject: str) -> set[str]:
    lowered = text.lower()
    found: set[str] = set()
    for pattern, label in ENTITY_PATTERNS:
        for match in re.finditer(pattern, lowered):
            found.add(label.format(*match.groups()) if label else match.group(0))
    if subject != "governance_owner":
        found.discard("owner")
    return found


def is_statement(passage: Passage, answers: Answers) -> bool:
    authority = float(str(value(answers, "authority")))
    return (
        not passage["duplicate_of"]
        and value(answers, "subject") != "noise"
        and value(answers, "nature") != "noise"
        and authority >= 1
        and len(passage["text"]) >= MIN_STATEMENT_LENGTH
    )


def strength(passage: Passage, answers: Answers) -> tuple[float, str, int, float]:
    nature = str(value(answers, "nature"))
    authority = float(str(value(answers, "authority")))
    risk = float(str(value(answers, "flags_risk")))
    return authority, passage["date"] or "", NATURE_RANK.get(nature, 0), risk


def strongest_per_source(passages: list[Passage], decisions: Decisions) -> list[Passage]:
    kept: dict[str, Passage] = {}
    for passage in sorted(passages, key=lambda item: strength(item, decisions[item["id"]]), reverse=True):
        kept.setdefault(passage["source_id"], passage)
    return list(kept.values())


def statements_by_subject(passages: list[Passage], decisions: Decisions) -> dict[str, list[Passage]]:
    grouped: dict[str, list[Passage]] = defaultdict(list)
    for passage in passages:
        answers = decisions.get(passage["id"])
        if answers and is_statement(passage, answers):
            grouped[str(value(answers, "subject"))].append(passage)
    return {subject: strongest_per_source(group, decisions) for subject, group in grouped.items()}


def ordered(first: Passage, second: Passage, subject: str) -> Pair | None:
    if first["source_id"] == second["source_id"]:
        return None
    if (first["date"] or "") > (second["date"] or ""):
        first, second = second, first
    return first, second, subject


def same_subject_pairs(grouped: dict[str, list[Passage]], found: dict[str, set[str]]) -> list[Pair | None]:
    pairs: list[Pair | None] = []
    for subject, passages in grouped.items():
        if subject == STATUS_SUBJECT:
            continue
        for index, first in enumerate(passages):
            pairs += [
                ordered(first, second, subject)
                for second in passages[index + 1 :]
                if found[first["id"]] & found[second["id"]]
            ]
    return pairs


def close_in_time(first: Passage, second: Passage) -> bool:
    gap = days_between(first["date"], second["date"])
    return gap is not None and abs(gap) <= STATUS_WINDOW_DAYS


def status_pairs(grouped: dict[str, list[Passage]], found: dict[str, set[str]]) -> list[Pair | None]:
    pairs: list[Pair | None] = []
    for report in grouped.get(STATUS_SUBJECT, []):
        for entity in sorted(found[report["id"]]):
            target = STATUS_TOPICS.get(entity)
            for passage in grouped.get(target or "", []):
                if close_in_time(passage, report) and entity in found[passage["id"]]:
                    pairs.append(ordered(passage, report, str(target)))
    return pairs


def shares_change_reference(first: set[str], second: set[str]) -> bool:
    return any(CHANGE_REFERENCE.match(entity) for entity in first & second)


def cross_subject_pairs(grouped: dict[str, list[Passage]], found: dict[str, set[str]]) -> list[Pair | None]:
    flat = [(subject, passage) for subject, passages in grouped.items() for passage in passages]
    pairs: list[Pair | None] = []
    for index, (first_subject, first) in enumerate(flat):
        for second_subject, second in flat[index + 1 :]:
            if first_subject != second_subject and shares_change_reference(
                found[first["id"]], found[second["id"]]
            ):
                label = "|".join(sorted((first_subject, second_subject)))
                pairs.append(ordered(first, second, label))
    return pairs


def candidate_pairs(passages: list[Passage], decisions: Decisions) -> list[Pair]:
    grouped = statements_by_subject(passages, decisions)
    found = {
        passage["id"]: entities(f"{passage['text']} {passage['source_id']}", subject)
        for subject, group in grouped.items()
        for passage in group
    }
    unique: dict[tuple[str, str], Pair] = {}
    for builder in (same_subject_pairs, status_pairs, cross_subject_pairs):
        for pair in builder(grouped, found):
            if pair:
                unique.setdefault((pair[0]["id"], pair[1]["id"]), pair)
    return sorted(unique.values(), key=lambda pair: (pair[2], pair[0]["date"] or "", pair[1]["date"] or ""))
