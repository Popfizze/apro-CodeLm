from __future__ import annotations

import re
from dataclasses import dataclass, field

from .geometry import center, connected_groups, lines_bbox
from .ingest import PageRef
from .rebar import has_rebar, norm_text

RE_ROW_LABEL = re.compile(r"^(TYPE\s*)?[A-Z0-9]{1,4}$")
MAX_STACK_LINES = 20


@dataclass
class Block:
    id: str
    page: PageRef = field(repr=False)
    lines: list[dict]
    kind: str = "stack"
    meta: dict = field(default_factory=dict)

    @property
    def bbox(self) -> list[float]:
        return [round(v, 1) for v in lines_bbox(self.lines)]

    @property
    def center(self) -> tuple[float, float]:
        x, y = center(self.bbox)
        return round(x, 1), round(y, 1)

    @property
    def texts(self) -> list[str]:
        return [ln["text"] for ln in self.lines]

    @property
    def text(self) -> str:
        return " / ".join(self.texts)


def _same_stack(a: dict, b: dict) -> bool:
    if a["dir"] != (1, 0) or b["dir"] != (1, 0):
        return False
    if abs(a["bbox"][0] - b["bbox"][0]) > 2.5:
        return False
    sa, sb = a["size"], b["size"]
    if max(sa, sb) / max(min(sa, sb), 0.1) > 1.35:
        return False
    h = max(a["bbox"][3] - a["bbox"][1], 1.0)
    gap = b["bbox"][1] - a["bbox"][3]
    return -0.6 * h <= gap <= 0.6 * h


def _table_header(lines: list[dict], type_cell: dict) -> list[dict] | None:
    y = (type_cell["bbox"][1] + type_cell["bbox"][3]) / 2
    header = [
        ln
        for ln in lines
        if abs((ln["bbox"][1] + ln["bbox"][3]) / 2 - y) < 3
        and 0 <= ln["bbox"][0] - type_cell["bbox"][0] < 500
    ]
    if not any(norm_text(ln["text"]).startswith("ARM") for ln in header):
        return None
    return sorted(header, key=lambda ln: ln["bbox"][0])


def _table_rows(lines: list[dict], type_cell: dict, header: list[dict]) -> list[list[dict]]:
    x_min, x_max = type_cell["bbox"][0] - 15, max(ln["bbox"][2] for ln in header) + 15
    row_height = type_cell["bbox"][3] - type_cell["bbox"][1]
    top = type_cell["bbox"][3]
    rows = []
    while True:
        row = [
            ln
            for ln in lines
            if top - 2 <= ln["bbox"][1] <= top + row_height * 0.9
            and x_min <= ln["bbox"][0] <= x_max
            and ln not in header
        ]
        if not row or not RE_ROW_LABEL.match(norm_text(min(row, key=lambda ln: ln["bbox"][0])["text"])):
            return rows
        row.sort(key=lambda ln: ln["bbox"][0])
        rows.append(row)
        top = max(ln["bbox"][3] for ln in row)


def find_tables(page: PageRef) -> list[tuple[list[dict], list[list[dict]]]]:
    tables = []
    for type_cell in page.lines:
        if norm_text(type_cell["text"]) != "TYPE":
            continue
        header = _table_header(page.lines, type_cell)
        rows = _table_rows(page.lines, type_cell, header) if header else []
        if rows:
            tables.append((header, rows))
    return tables


def _table_blocks(page: PageRef, tables: list) -> list[Block]:
    blocks = []
    for ti, (header, rows) in enumerate(tables):
        header_text = " | ".join(ln["text"] for ln in header)
        header_cells = [ln["text"] for ln in header]
        header_x = [ln["bbox"][0] for ln in header]
        for ri, row in enumerate(rows):
            meta = {
                "header": header_text,
                "cells": [ln["text"] for ln in row],
                "header_cells": header_cells,
                "header_x": header_x,
            }
            blocks.append(Block(f"{page.key}_t{ti}r{ri}", page, row, kind="table_row", meta=meta))
    return blocks


def _stack_links(lines: list[dict]):
    by_x: dict[int, list[int]] = {}
    for i, ln in enumerate(lines):
        by_x.setdefault(int(ln["bbox"][0] // 3), []).append(i)
    for i, line in enumerate(lines):
        column = int(line["bbox"][0] // 3)
        for neighbour in (column - 1, column, column + 1):
            for j in by_x.get(neighbour, []):
                if j != i and _same_stack(line, lines[j]):
                    yield i, j


def _stack_blocks(page: PageRef, lines: list[dict]) -> list[Block]:
    lines = sorted(lines, key=lambda ln: (round(ln["bbox"][0]), ln["bbox"][1]))
    stacks = []
    for group in connected_groups(len(lines), _stack_links(lines)):
        stack = sorted((lines[i] for i in group), key=lambda ln: ln["bbox"][1])
        if any(has_rebar(ln["text"]) for ln in stack) and len(stack) <= MAX_STACK_LINES:
            stacks.append(stack)
    return [Block(f"{page.key}_b{n}", page, stack) for n, stack in enumerate(stacks)]


def segment_page(page: PageRef) -> list[Block]:
    tables = find_tables(page)
    in_table = {id(ln) for header, rows in tables for ln in header + [cell for row in rows for cell in row]}
    rest = [ln for ln in page.lines if id(ln) not in in_table]
    return _table_blocks(page, tables) + _stack_blocks(page, rest)
