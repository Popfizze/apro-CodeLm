import re
from collections.abc import Iterator
from typing import Any

import fitz

from pipeline.dates import find_date
from pipeline.records import Passage, SourceRef, make_passage

PAGE_LIMIT = 1500
CHUNK_SIZE = 600
SUPPLIER = re.compile(r"Fournisseur \| ([^|]+)")
REQUESTER = re.compile(r"Demandeur \| ([^|]+)")


def pdf_pages(data: bytes) -> Iterator[tuple[int, list[str]]]:
    document = fitz.open(stream=data, filetype="pdf")
    for number, page in enumerate(document, start=1):
        yield number, [line.strip() for line in page.get_text().splitlines() if line.strip()]


def pdf_author(text: str) -> str | None:
    supplier = SUPPLIER.search(text)
    if supplier and "FACTURE" in text:
        return supplier.group(1).strip()
    requester = REQUESTER.search(text)
    return requester.group(1).strip() if requester else None


def chunks_of(lines: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = [[]]
    for line in lines:
        chunks[-1].append(line)
        if sum(len(part) for part in chunks[-1]) > CHUNK_SIZE:
            chunks.append([])
    return [chunk for chunk in chunks if chunk]


def page_passages(
    source: SourceRef, number: int, lines: list[str], prefix: tuple[str, str], fields: dict[str, Any]
) -> list[Passage]:
    locator_prefix, suffix_prefix = prefix
    text = " | ".join(lines)
    found = find_date(" ".join(lines))
    if len(text) <= PAGE_LIMIT:
        page_id, page_locator = f"{suffix_prefix}p{number}", f"{locator_prefix}p.{number}"
        return [
            make_passage(source, page_id, page_locator, text, date=found, author=pdf_author(text), **fields)
        ]
    return [
        make_passage(
            source,
            f"{suffix_prefix}p{number}b{block}",
            f"{locator_prefix}p.{number} bloc {block}",
            " | ".join(chunk),
            date=found,
            **fields,
        )
        for block, chunk in enumerate(chunks_of(lines), start=1)
    ]


def ingest_pdf(
    data: bytes, source: SourceRef, prefix: tuple[str, str] = ("", ""), **fields: Any
) -> list[Passage]:
    passages: list[Passage] = []
    for number, lines in pdf_pages(data):
        passages.extend(page_passages(source, number, lines, prefix, fields))
    return passages
