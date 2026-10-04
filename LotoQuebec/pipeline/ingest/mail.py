import email
import re
import sys
from email import policy
from email.message import EmailMessage, Message
from email.utils import parsedate_to_datetime
from pathlib import Path

from pipeline.corpus import kind_for, relative_path
from pipeline.dates import find_date
from pipeline.ingest.captures import CaptureTranscriber, capture_passages
from pipeline.ingest.pdf import ingest_pdf
from pipeline.records import Passage, SourceRef, make_passage
from pipeline.settings import CORPUS_DIR

PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
QUOTE_INTRO = re.compile(r"Le\s+(.+?),\s+(.+?)\s+écrivait", re.IGNORECASE)


def sender_name(message: Message) -> str:
    sender = message["From"]
    addresses = getattr(sender, "addresses", ())
    if addresses and addresses[0].display_name:
        return str(addresses[0].display_name)
    return str(sender)


def header_text(message: Message) -> str:
    lines = [f"De : {message['From']}", f"À : {message['To']}"]
    if message["Cc"]:
        lines.append(f"Cc : {message['Cc']}")
    lines += [f"Date : {message['Date']}", f"Objet : {message['Subject']}"]
    return "\n".join(lines)


def quoted_passage(source: SourceRef, number: int, lines: list[str], sent: str | None) -> Passage:
    text = "\n".join(line.lstrip("> ").rstrip() for line in lines)
    intro = QUOTE_INTRO.search(text)
    quoted_date = find_date(intro.group(1)) if intro else None
    return make_passage(
        source,
        f"b{number}",
        f"corps §{number} (citation)",
        text,
        date=quoted_date or sent,
        author=intro.group(2).strip() if intro else None,
    )


def body_passages(source: SourceRef, body: str, sent: str | None, author: str) -> list[Passage]:
    paragraphs = [paragraph.strip() for paragraph in PARAGRAPH_BREAK.split(body) if paragraph.strip()]
    passages = []
    for number, paragraph in enumerate(paragraphs, start=1):
        lines = paragraph.splitlines()
        if all(line.startswith(">") for line in lines):
            passages.append(quoted_passage(source, number, lines, sent))
        else:
            passages.append(
                make_passage(source, f"b{number}", f"corps §{number}", paragraph, date=sent, author=author)
            )
    return passages


def attachment_kind(name: str) -> str:
    hits = list(CORPUS_DIR.rglob(name))
    if hits:
        return kind_for(relative_path(hits[0]))
    return "invoice" if name.upper().startswith("INV-") else "project_doc"


def attachment_passages(
    source: SourceRef, number: int, part: Message, sent: str | None, transcriber: CaptureTranscriber
) -> list[Passage]:
    name = part.get_filename() or f"piece{number}"
    data = part.get_payload(decode=True)
    if not isinstance(data, bytes):
        return []
    attached = SourceRef(source.source_id, source.path, attachment_kind(name))
    prefix = (f"PJ: {name} ", f"att{number}")
    fields = {"attachment_of": source.source_id, "attachment_name": name}
    if name.lower().endswith(".pdf"):
        return ingest_pdf(data, attached, prefix, **fields)
    if name.lower().endswith(".png"):
        image = SourceRef(source.source_id, source.path, "image")
        return capture_passages(image, data, transcriber, sent, prefix, **fields)
    print(f"[ingest] unsupported attachment {name} in {source.path}", file=sys.stderr)
    return []


def ingest_eml(path: Path, source: SourceRef, transcriber: CaptureTranscriber) -> list[Passage]:
    message = email.message_from_bytes(path.read_bytes(), _class=EmailMessage, policy=policy.default)
    sent = parsedate_to_datetime(message["Date"]).isoformat() if message["Date"] else None
    author = sender_name(message)
    passages = [make_passage(source, "hdr", "en-tête", header_text(message), date=sent, author=author)]
    body = message.get_body(preferencelist=("plain",))
    if isinstance(body, EmailMessage):
        passages += body_passages(source, body.get_content(), sent, author)
    for number, part in enumerate(message.iter_attachments(), start=1):
        passages += attachment_passages(source, number, part, sent, transcriber)
    return passages
