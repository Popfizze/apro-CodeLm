import re
from dataclasses import dataclass
from pathlib import Path

from pipeline.dates import find_date, with_time
from pipeline.records import Passage, SourceRef, make_passage

TRANSCRIPT_LINE = re.compile(r"^(\d{1,2}:\d{2})\s+(?:-\s+)?(?:\[(.+?)\]|(.+?)\s*:\s+(.*)|(.+))$")
TICKET_COMMENT = re.compile(
    r"^(\d{1,2}\s+[A-Za-zéû]+\.?(?:\s+\d{4})?)(?:\s+(\d{1,2}:\d{2}))?\s+-\s+(?:([^:]{1,40}?)\s+:\s+)?(.*)$"
)
LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s")
NUMBERED_ITEM = re.compile(r"^\d+\.\s")
REQUESTER = re.compile(r"^Demandeur\s*:\s*(.+)$", re.MULTILINE)

Line = tuple[int, str]


@dataclass(frozen=True)
class TextDocument:
    source: SourceRef
    date: str | None


def is_item_line(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith(("- ", "* ")):
        return True
    patterns = (TRANSCRIPT_LINE, TICKET_COMMENT, LOG_LINE, NUMBERED_ITEM)
    return any(pattern.match(stripped) for pattern in patterns)


def looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    short_label = len(stripped) <= 40 and not stripped.endswith(".") and ":" not in stripped[:-1]
    return (stripped.startswith("#") or short_label) and not is_item_line(stripped)


def clean_heading(line: str) -> str:
    return line.strip().lstrip("# ").rstrip(" :")


def blocks_of(lines: list[str]) -> list[list[Line]]:
    blocks: list[list[Line]] = []
    current: list[Line] = []
    for number, line in enumerate(lines, start=1):
        if line.strip():
            current.append((number, line.rstrip()))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def line_span(first: int, last: int) -> str:
    return f"ligne {first}" if first == last else f"lignes {first}-{last}"


def section_locator(heading: str | None, span: str) -> str:
    return f"§{heading}, {span}" if heading else span


def document_date(raw: str, lines: list[str]) -> str | None:
    header = [line for line in lines[:6] if line.strip() and not line.strip().startswith("- ")]
    found = find_date("\n".join(header))
    if found is None and LOG_LINE.match(raw):
        return find_date(raw)
    return found


def header_passage(document: TextDocument, block: list[Line]) -> Passage:
    text = "\n".join(line for _, line in block)
    requester = REQUESTER.search(text)
    return make_passage(
        document.source,
        f"L{block[0][0]}",
        f"en-tête ({line_span(block[0][0], block[-1][0])})",
        text,
        date=document.date,
        author=requester.group(1).strip() if requester else None,
    )


def group_passage(document: TextDocument, block: list[Line], heading: str | None) -> Passage:
    locator = section_locator(heading, line_span(block[0][0], block[-1][0]))
    text = "\n".join(line for _, line in block)
    return make_passage(document.source, f"L{block[0][0]}", locator, text, date=document.date)


def transcript_item(document: TextDocument, number: int, line: str, section: str) -> Passage | None:
    match = TRANSCRIPT_LINE.match(line)
    if not match or not document.date:
        return None
    clock = match.group(1)
    return make_passage(
        document.source,
        f"L{number}",
        f"{section}ligne {number} [{clock}]",
        line,
        date=with_time(document.date, clock),
        author=(match.group(3) or "").strip() or None,
    )


def ticket_comment_item(document: TextDocument, number: int, line: str, section: str) -> Passage | None:
    match = TICKET_COMMENT.match(line)
    if not match:
        return None
    day, clock, author = match.group(1), match.group(2), (match.group(3) or "").strip() or None
    found = find_date(day)
    if found and clock:
        found = with_time(found, clock)
    stamp = day + (f" {clock}" if clock else "") + (f" - {author}" if author else "")
    return make_passage(
        document.source,
        f"L{number}",
        f"{section}ligne {number} [{stamp}]",
        line,
        date=found or document.date,
        author=author,
    )


def log_item(document: TextDocument, number: int, line: str, section: str) -> Passage | None:
    match = LOG_LINE.match(line)
    if not match:
        return None
    stamp = match.group(1)
    return make_passage(
        document.source, f"L{number}", f"ligne {number} [{stamp}]", line, date=stamp.replace("Z", "+00:00")
    )


def item_passage(document: TextDocument, number: int, line: str, heading: str | None) -> Passage:
    section = f"§{heading}, " if heading else ""
    for builder in (transcript_item, ticket_comment_item, log_item):
        passage = builder(document, number, line, section)
        if passage:
            return passage
    return make_passage(document.source, f"L{number}", f"{section}ligne {number}", line, date=document.date)


def is_lone_heading(lines: list[Line]) -> bool:
    return len(lines) == 1 and looks_like_heading(lines[0][1])


def itemized_passages(document: TextDocument, block: list[Line], heading: str | None) -> list[Passage]:
    passages: list[Passage] = []
    pending: list[Line] = []
    for number, line in block:
        if not is_item_line(line):
            pending.append((number, line))
            continue
        if pending and not is_lone_heading(pending):
            passages.append(group_passage(document, pending, heading))
        pending = []
        passages.append(item_passage(document, number, line.strip(), heading))
    if pending:
        passages.append(group_passage(document, pending, heading))
    return passages


def block_passages(document: TextDocument, block: list[Line], heading: str | None) -> list[Passage]:
    if any(is_item_line(line) for _, line in block):
        return itemized_passages(document, block, heading)
    return [group_passage(document, block, heading)]


def block_heading(block: list[Line]) -> str | None:
    first = block[0][1]
    return clean_heading(first) if looks_like_heading(first) else None


def ingest_text(path: Path, source: SourceRef) -> list[Passage]:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    document = TextDocument(source, document_date(raw, lines))
    passages: list[Passage] = []
    carried: str | None = None
    for index, block in enumerate(blocks_of(lines)):
        if index == 0 and not is_item_line(block[0][1]):
            passages.append(header_passage(document, block))
            continue
        if is_lone_heading(block):
            carried = clean_heading(block[0][1])
            continue
        heading = block_heading(block) or carried
        carried = None
        passages.extend(block_passages(document, block, heading))
    return passages
