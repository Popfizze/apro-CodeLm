from pathlib import Path
from typing import Any

from pipeline.evidence import EvidenceError, citations_in, resolve_citations, verify_citations
from pipeline.jsonio import read_json
from pipeline.records import Passage
from pipeline.settings import CONTENT, CORPUS_DIR, ROOT

CONTENT_FILE = CONTENT / "kb.json"
SECTIONS = (
    "meta",
    "sources",
    "personnes",
    "sujets",
    "evenements",
    "decisions",
    "engagements_actions",
    "risques",
    "contradictions",
    "manquants",
    "finances",
    "golive",
    "reponses",
    "brief",
    "exemples",
)
QUESTION_IDS = [f"Q{number:02d}" for number in range(1, 11)]
CITED_LISTS = {
    "reponses": "sources",
    "exemples": "sources",
    "decisions": "sources",
    "engagements_actions": "preuves",
    "evenements": "preuves",
}
SOURCE_LISTS = ("personnes", "sujets", "risques")
CITATION_KEYS = {"passage", "citation"}

Content = dict[str, Any]


def load_content(path: Path = CONTENT_FILE) -> Content:
    content: Content = read_json(path)
    return content


def section_problems(content: Content) -> list[str]:
    missing = [f"missing section {name!r}" for name in SECTIONS if name not in content]
    unknown = [f"unexpected section {name!r}" for name in content if name not in SECTIONS]
    return missing + unknown


def answer_problems(content: Content) -> list[str]:
    found = [answer.get("q") for answer in content.get("reponses", [])]
    if found != QUESTION_IDS:
        return [f"reponses must be {QUESTION_IDS[0]}..{QUESTION_IDS[-1]} in order, found {found}"]
    return []


def uncited_items(content: Content) -> list[str]:
    problems = []
    for section, key in CITED_LISTS.items():
        for index, item in enumerate(content.get(section, [])):
            if not item.get(key):
                problems.append(f"{section}.{index}: no citation in {key!r}")
    for index, item in enumerate(content.get("contradictions", [])):
        for side in ("version_A", "version_B"):
            if not item.get(side, {}).get("preuves"):
                problems.append(f"contradictions.{index}.{side}: no citation")
    for index, item in enumerate(content.get("golive", {}).get("conditions", [])):
        if not item.get("sources"):
            problems.append(f"golive.conditions.{index}: no citation")
    return problems


def citation_shape_problems(content: Content) -> list[str]:
    return [
        f"{where}: a citation holds exactly {sorted(CITATION_KEYS)}, found {sorted(citation)}"
        for where, citation in citations_in(content)
        if set(citation) != CITATION_KEYS
    ]


def source_reference_problems(content: Content, known: set[str]) -> list[str]:
    described = set(content.get("sources", {}))
    problems = [f"sources.{name}: not a corpus source" for name in sorted(described - known)]
    problems += [f"sources: no description for {name}" for name in sorted(known - described)]
    for section in SOURCE_LISTS:
        for index, item in enumerate(content.get(section, [])):
            unknown = [name for name in item.get("sources", []) if name not in known]
            if unknown:
                problems.append(f"{section}.{index}.sources: unknown sources {unknown}")
    return problems


def validate(content: Content, passages: dict[str, Passage], known_sources: set[str]) -> int:
    problems = section_problems(content) + answer_problems(content) + uncited_items(content)
    problems += citation_shape_problems(content) + source_reference_problems(content, known_sources)
    count, evidence = verify_citations(content, passages)
    problems += evidence
    if problems:
        raise EvidenceError(problems)
    return count


def described_sources(content: Content, registry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    descriptions = content["sources"]
    return [{**entry, **descriptions[entry["id"]]} for entry in registry]


def build_knowledge(
    content: Content, passages: list[Passage], registry: list[dict[str, Any]], version: str
) -> dict[str, Any]:
    by_id = {passage["id"]: passage for passage in passages}
    count = validate(content, by_id, {entry["id"] for entry in registry})
    knowledge: dict[str, Any] = resolve_citations({key: content[key] for key in SECTIONS}, by_id)
    knowledge["meta"] = {
        **content["meta"],
        "version": version,
        "corpus": CORPUS_DIR.relative_to(ROOT).as_posix(),
        "nb_sources": len(registry),
        "nb_passages": len(passages),
        "nb_citations_verifiees": count,
    }
    knowledge["sources"] = described_sources(content, registry)
    return knowledge
