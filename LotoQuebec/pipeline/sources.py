import email
from collections import Counter
from email import policy
from pathlib import Path
from typing import Any

from pipeline.corpus import relative_path, sha256_bytes, source_ref
from pipeline.dedup import identical_sources
from pipeline.records import Passage


def attachments_of(path: Path, hashes: dict[str, str]) -> list[dict[str, Any]]:
    if path.suffix.lower() != ".eml":
        return []
    message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    found = []
    for part in message.walk():
        if part.get_content_disposition() != "attachment":
            continue
        data = part.get_payload(decode=True)
        digest = sha256_bytes(data) if isinstance(data, bytes) else None
        found.append(
            {"name": part.get_filename(), "sha256": digest, "identical_to": hashes.get(digest or "")}
        )
    return found


def source_registry(files: list[Path], passages: list[Passage]) -> list[dict[str, Any]]:
    counts = Counter(passage["source_id"] for passage in passages)
    copies = identical_sources(passages)
    hashes = {sha256_bytes(path.read_bytes()): source_ref(relative_path(path)).source_id for path in files}
    registry = []
    for path in files:
        source = source_ref(relative_path(path))
        registry.append(
            {
                "id": source.source_id,
                "path": source.path,
                "kind": source.kind,
                "bytes": path.stat().st_size,
                "sha256": sha256_bytes(path.read_bytes()),
                "passages": counts[source.source_id],
                "identical_to": copies.get(source.source_id),
                "attachments": attachments_of(path, hashes),
            }
        )
    return registry
