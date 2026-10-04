from dataclasses import dataclass
from typing import Any

from pipeline.text import content_hash

Passage = dict[str, Any]
Answer = dict[str, Any]
Answers = dict[str, Answer]
Question = dict[str, Any]
Questions = dict[str, Question]


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    path: str
    kind: str


def make_passage(source: SourceRef, suffix: str, locator: str, text: str, **fields: Any) -> Passage:
    passage: Passage = {
        "id": f"{source.source_id}:{suffix}",
        "source_id": source.source_id,
        "path": source.path,
        "kind": source.kind,
        "locator": locator,
        "date": None,
        "author": None,
        "text": text.strip(),
        "attachment_of": None,
        "duplicate_of": None,
        "sha256": content_hash(text),
    }
    passage.update(fields)
    return passage
