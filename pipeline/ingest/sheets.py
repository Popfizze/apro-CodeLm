import csv
from pathlib import Path
from typing import Any

import openpyxl

from pipeline.dates import date_from_file_stem, find_date
from pipeline.records import Passage, SourceRef, make_passage

NOTE_COLUMNS = ("comment", "note")


def header_of(row: tuple[Any, ...]) -> list[str]:
    return [str(cell.value) if cell.value is not None else cell.column_letter for cell in row]


def filled_cells(header: list[str], row: tuple[Any, ...]) -> dict[str, str]:
    pairs = zip(header, row, strict=False)
    return {cell.coordinate: f"{name}: {cell.value}" for name, cell in pairs if cell.value not in (None, "")}


def note_date(header: list[str], row: tuple[Any, ...]) -> str | None:
    found = None
    for name, cell in zip(header, row, strict=False):
        if name.lower().startswith(NOTE_COLUMNS) and cell.value not in (None, ""):
            found = find_date(str(cell.value)) or found
    return found


def row_passage(
    source: SourceRef, sheet: Any, prefix: str, header: list[str], row: Any, doc_date: str | None
) -> Passage | None:
    cells = filled_cells(header, row)
    if not cells:
        return None
    number = row[0].row
    return make_passage(
        source,
        f"{prefix}R{number}",
        f"{sheet.title}!{row[0].coordinate}:{row[-1].coordinate} (ligne {number})",
        " | ".join(cells.values()),
        date=note_date(header, row) or doc_date,
        doc_date=doc_date,
        sheet=sheet.title,
        cells=cells,
    )


def comment_passage(source: SourceRef, sheet: Any, prefix: str, cell: Any, doc_date: str | None) -> Passage:
    comment_date = find_date(cell.comment.text) or doc_date
    author = cell.comment.author or "inconnu"
    dated = f", {comment_date}" if comment_date else ""
    return make_passage(
        source,
        f"{prefix}C{cell.coordinate}",
        f"{sheet.title}!{cell.coordinate} (commentaire de {author}{dated})",
        f"Commentaire sur {cell.coordinate} ({cell.value}) : {cell.comment.text}",
        date=comment_date,
        author=cell.comment.author,
        doc_date=doc_date,
    )


def sheet_passages(source: SourceRef, sheet: Any, prefix: str, doc_date: str | None) -> list[Passage]:
    rows = list(sheet.iter_rows())
    if not rows:
        return []
    header = header_of(rows[0])
    passages = [row_passage(source, sheet, prefix, header, row, doc_date) for row in rows[1:]]
    comments = [
        comment_passage(source, sheet, prefix, cell, doc_date) for row in rows for cell in row if cell.comment
    ]
    return [passage for passage in passages if passage] + comments


def ingest_xlsx(path: Path, source: SourceRef) -> list[Passage]:
    workbook = openpyxl.load_workbook(path)
    doc_date = date_from_file_stem(path.stem)
    several = len(workbook.worksheets) > 1
    passages: list[Passage] = []
    for number, sheet in enumerate(workbook.worksheets, start=1):
        prefix = f"S{number}" if several else ""
        passages.extend(sheet_passages(source, sheet, prefix, doc_date))
    return passages


def ingest_csv(path: Path, source: SourceRef) -> list[Passage]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    passages = []
    for number, row in enumerate(rows[1:], start=2):
        text = " | ".join(f"{name}: {value}" for name, value in zip(header, row, strict=False))
        passages.append(make_passage(source, f"L{number}", f"ligne {number}", text, date=find_date(text)))
    return passages
