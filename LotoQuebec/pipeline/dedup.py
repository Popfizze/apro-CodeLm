from collections import defaultdict

from pipeline.records import Passage

MIN_DUPLICATE_LENGTH = 40


def origin(passage: Passage) -> tuple[str, str | None]:
    return passage["source_id"], passage["attachment_of"]


def canonical_order(passage: Passage) -> tuple[bool, str, str]:
    return passage["attachment_of"] is not None, passage["path"], passage["id"]


def source_signatures(passages: list[Passage]) -> dict[str, tuple[tuple[str, str], ...]]:
    signatures: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for passage in passages:
        if passage["attachment_of"] is None:
            suffix = passage["id"].split(":", 1)[1]
            signatures[passage["source_id"]].append((suffix, passage["sha256"]))
    return {source: tuple(sorted(signature)) for source, signature in signatures.items()}


def identical_sources(passages: list[Passage]) -> dict[str, str]:
    first_by_signature: dict[tuple[tuple[str, str], ...], str] = {}
    copies: dict[str, str] = {}
    paths = {passage["source_id"]: passage["path"] for passage in passages}
    for source, signature in sorted(source_signatures(passages).items(), key=lambda item: paths[item[0]]):
        original = first_by_signature.setdefault(signature, source)
        if original != source:
            copies[source] = original
    return copies


def mark_file_copies(passages: list[Passage], copies: dict[str, str]) -> None:
    for passage in passages:
        original = copies.get(passage["source_id"])
        if original and passage["attachment_of"] is None:
            passage["duplicate_of"] = f"{original}:{passage['id'].split(':', 1)[1]}"


def mark_text_copies(passages: list[Passage]) -> None:
    canonical: dict[str, Passage] = {}
    for passage in sorted(passages, key=canonical_order):
        if passage["duplicate_of"] or len(passage["text"]) < MIN_DUPLICATE_LENGTH:
            continue
        first = canonical.setdefault(passage["sha256"], passage)
        if first is not passage and origin(first) != origin(passage):
            passage["duplicate_of"] = first["id"]


def mark_duplicates(passages: list[Passage]) -> dict[str, str]:
    for passage in passages:
        passage["duplicate_of"] = None
    copies = identical_sources(passages)
    mark_file_copies(passages, copies)
    mark_text_copies(passages)
    return copies
