import re
import sys
from collections.abc import Callable
from pathlib import Path

from pipeline.corpus import relative_path, source_ref
from pipeline.dates import find_date
from pipeline.dedup import mark_duplicates
from pipeline.ingest.captures import CaptureTranscriber, capture_passages
from pipeline.ingest.mail import ingest_eml
from pipeline.ingest.pdf import ingest_pdf
from pipeline.ingest.plain_text import ingest_text
from pipeline.ingest.sheets import ingest_csv, ingest_xlsx
from pipeline.records import Passage, SourceRef

CREATED = re.compile(r"Créé\s*:\s*(.+)")
NATURAL_PARTS = re.compile(r"(\d+)")

Reader = Callable[[Path, SourceRef], list[Passage]]
READERS: dict[str, Reader] = {
    ".txt": ingest_text,
    ".md": ingest_text,
    ".xlsx": ingest_xlsx,
    ".csv": ingest_csv,
    ".pdf": lambda path, source: ingest_pdf(path.read_bytes(), source),
}


class Ingester:
    def __init__(self, transcriber: CaptureTranscriber | None = None) -> None:
        self.transcriber = transcriber or CaptureTranscriber()
        self.ticket_dates: dict[str, str | None] = {}

    def read(self, path: Path, source: SourceRef) -> list[Passage]:
        extension = path.suffix.lower()
        if extension == ".eml":
            return ingest_eml(path, source, self.transcriber)
        if extension == ".png":
            ticket = path.stem.split("_")[0]
            fallback = self.ticket_dates.get(ticket)
            return capture_passages(source, path.read_bytes(), self.transcriber, fallback)
        reader = READERS.get(extension)
        if reader is None:
            print(f"[ingest] unsupported file type: {source.path}", file=sys.stderr)
            return []
        return reader(path, source)

    def remember_ticket_date(self, source: SourceRef, passages: list[Passage]) -> None:
        if source.kind != "ticket" or not passages:
            return
        created = CREATED.search(passages[0]["text"])
        if created:
            self.ticket_dates[source.source_id] = find_date(created.group(1))

    def ingest_file(self, path: Path, source: SourceRef) -> list[Passage]:
        passages = self.read(path, source)
        self.remember_ticket_date(source, passages)
        if not passages:
            print(f"[ingest] no passage from {source.path}", file=sys.stderr)
        return passages


def passage_order(passage: Passage) -> tuple[str, bool, list[object]]:
    suffix = passage["id"].split(":", 1)[1]
    parts: list[object] = (
        [""]
        if suffix == "hdr"
        else [int(part) if part.isdigit() else part for part in NATURAL_PARTS.split(suffix)]
    )
    return passage["path"], passage["attachment_of"] is not None, parts


def ingest_corpus(files: list[Path], ingester: Ingester | None = None) -> list[Passage]:
    reader = ingester or Ingester()
    passages: list[Passage] = []
    for path in sorted(files, key=lambda item: item.suffix.lower() == ".png"):
        passages += reader.ingest_file(path, source_ref(relative_path(path)))
    mark_duplicates(passages)
    passages.sort(key=passage_order)
    ids = [passage["id"] for passage in passages]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate passage ids")
    return passages
