import re
from collections.abc import Iterator
from typing import Any

from pipeline.records import Passage
from pipeline.text import contains_quote

MAX_QUOTE_LENGTH = 320
COLUMN_LETTERS = re.compile(r"[A-Z]+")

Node = dict[str, Any]


class EvidenceError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__(f"{len(problems)} evidence discrepancies:\n  " + "\n  ".join(problems))
        self.problems = problems


def citations_in(node: Any, path: str = "") -> Iterator[tuple[str, Node]]:
    if isinstance(node, dict):
        if "passage" in node:
            yield path, node
            return
        for key, value in node.items():
            yield from citations_in(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from citations_in(value, f"{path}.{index}")


def citation_problems(where: str, citation: Node, passages: dict[str, Passage]) -> list[str]:
    passage = passages.get(str(citation.get("passage")))
    quote = str(citation.get("citation") or "")
    if passage is None:
        return [f"{where}: unknown passage {citation.get('passage')!r}"]
    if not quote.strip():
        return [f"{where}: empty quote for {passage['id']}"]
    if len(quote) > MAX_QUOTE_LENGTH:
        return [f"{where}: quote longer than {MAX_QUOTE_LENGTH} characters for {passage['id']}"]
    if not contains_quote(passage["text"], quote):
        return [f"{where}: quote not found in {passage['id']} ({passage['locator']}): {quote!r}"]
    return []


def cell_locator(passage: Passage, quote: str) -> str | None:
    cells: dict[str, str] = passage.get("cells") or {}
    hits = [coordinate for coordinate, text in cells.items() if contains_quote(text, quote)]
    if len(hits) != 1:
        return None
    row = COLUMN_LETTERS.sub("", hits[0])
    return f"{passage['sheet']}!{hits[0]} (ligne {row})"


def resolved(citation: Node, passage: Passage) -> Node:
    quote = str(citation["citation"])
    return {
        "passage": passage["id"],
        "source": passage["source_id"],
        "fichier": passage["path"],
        "repere": cell_locator(passage, quote) or passage["locator"],
        "citation": quote,
    }


def resolve_citations(node: Any, passages: dict[str, Passage]) -> Any:
    if isinstance(node, dict):
        if "passage" in node:
            return resolved(node, passages[str(node["passage"])])
        return {key: resolve_citations(value, passages) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve_citations(value, passages) for value in node]
    return node


def verify_citations(content: Any, passages: dict[str, Passage]) -> tuple[int, list[str]]:
    found = list(citations_in(content))
    problems = [
        problem for where, citation in found for problem in citation_problems(where, citation, passages)
    ]
    return len(found), problems
