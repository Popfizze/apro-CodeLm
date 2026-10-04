from __future__ import annotations

import sys

import fitz

from .style import (
    BORDER,
    BORDER_SOFT,
    CYAN,
    INK,
    LOGO_SVG,
    STATUS_COLORS,
    STATUS_LABEL,
    TEXT,
    corner_radius,
    rgb,
)

INDEX_RECT = fitz.paper_rect("letter")
INDEX_LINES_PER_PAGE = 40
INDEX_TOP = 132
INDEX_STEP = 15
MARGIN = 42
MAX_GAP_TEXT = 52
COLS = {"feuillet": 52, "element": 100, "statut": 158, "ecart": 252, "plan": 476, "atelier": 520}
HEADERS = (
    ("feuillet", "FEUILLET"),
    ("element", "ÉLÉMENT"),
    ("statut", "STATUT"),
    ("ecart", "ÉCART"),
    ("plan", "PLAN"),
    ("atelier", "ATELIER"),
)
ATTR_SHORT = {
    "diametre": "diam.",
    "quantite": "qté",
    "espacement": "esp.",
    "espacement_mm": "esp.",
    "longueur": "long.",
    "longueur_mm": "long.",
}


def rect_radius(rect: fitz.Rect, radius: float) -> tuple[float, float]:
    return corner_radius(rect.width, rect.height, radius)


def link(page: fitz.Page, rect: fitz.Rect, target_page: int, target_point: fitz.Point | None = None) -> None:
    target = target_point or fitz.Point(0, 0)
    page.insert_link({"kind": fitz.LINK_GOTO, "from": rect, "page": target_page, "to": target, "zoom": 0})


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def gap_summary(ecart: dict) -> str:
    attribute = ATTR_SHORT.get(str(ecart.get("attribut")), str(ecart.get("attribut") or ""))
    head = " ".join(x for x in (ecart.get("repere"), attribute) if x)
    return f"{head} {_fmt(ecart.get('plan'))} -> {_fmt(ecart.get('atelier'))}"


def _gap_text(finding: dict) -> str:
    ecarts = finding.get("ecarts") or []
    parts = [gap_summary(e).strip() for e in ecarts[:2]]
    if len(ecarts) > 2:
        parts.append("...")
    text = " ; ".join(parts)
    return text if len(text) <= MAX_GAP_TEXT else text[:49] + "..."


def logo_pdf() -> fitz.Document | None:
    try:
        svg = LOGO_SVG.read_text(encoding="utf-8").replace("currentColor", INK)
        with fitz.open(stream=svg.encode("utf-8"), filetype="svg") as drawing:
            return fitz.open("pdf", drawing.convert_to_pdf())
    except Exception as exc:
        print(f"[annotate] logo skipped: {exc}", file=sys.stderr)
        return None


def _chip(page: fitz.Page, x: float, y: float, statut: str) -> None:
    text = STATUS_LABEL[statut].upper()
    size = 6.3
    width = fitz.get_text_length(text, fontname="hebo", fontsize=size)
    rect = fitz.Rect(x, y - size - 2.2, x + width + 9, y + 2.6)
    color, fill = STATUS_COLORS[statut]
    page.draw_rect(rect, color=None, fill=rgb(fill), width=0, radius=rect_radius(rect, 99))
    page.insert_text((x + 4.5, y), text, fontname="hebo", fontsize=size, color=rgb(color))


def _index_frame(page: fitz.Page, project: str, logo: fitz.Document | None, n_rows: int) -> None:
    width = INDEX_RECT.width
    if logo is not None:
        logo_rect, height = logo[0].rect, 22.0
        page.show_pdf_page(
            fitz.Rect(MARGIN, 34, MARGIN + height * logo_rect.width / logo_rect.height, 34 + height), logo, 0
        )
    title = f"PDF ANNOTÉS - {str(project).upper()}"
    page.insert_text((MARGIN, 80), title, fontname="helv", fontsize=12.5, color=rgb(INK))
    page.draw_line((MARGIN, 88), (width - MARGIN, 88), color=rgb(CYAN), width=1.2)
    top = INDEX_TOP - 28
    box = fitz.Rect(MARGIN, top - 4, width - MARGIN, INDEX_TOP + (n_rows - 1) * INDEX_STEP + 7)
    page.draw_rect(box, color=rgb(BORDER), width=0.8, radius=rect_radius(box, 7))
    for key, label in HEADERS:
        page.insert_text((COLS[key], top + 9), label, fontname="hebo", fontsize=6.6, color=rgb(TEXT))
    page.draw_line((MARGIN + 0.4, top + 14.5), (width - MARGIN - 0.4, top + 14.5), color=rgb(CYAN), width=0.9)


def _page_link(page: fitz.Page, side: str, y: float, mark: tuple) -> None:
    text, x = f"p. {mark[0] + 1}", COLS[side]
    page.insert_text((x, y), text, fontname="helv", fontsize=8, color=rgb(CYAN))
    width = fitz.get_text_length(text, fontname="helv", fontsize=8)
    link(page, fitz.Rect(x - 2, y - 9, x + width + 2, y + 3), mark[0], fitz.Point(mark[1].x0, mark[1].y0))


def _index_row(page: fitz.Page, k: int, finding: dict, marks: dict) -> None:
    row = k % INDEX_LINES_PER_PAGE
    y = INDEX_TOP + row * INDEX_STEP
    if row:
        page.draw_line(
            (MARGIN + 8, y - 10.5),
            (INDEX_RECT.width - MARGIN - 8, y - 10.5),
            color=rgb(BORDER_SOFT),
            width=0.5,
        )
    sheet, element = str(finding.get("feuillet") or "-"), str(finding.get("element") or "?")
    page.insert_text((COLS["feuillet"], y), sheet, fontname="hebo", fontsize=8, color=rgb(INK))
    page.insert_text((COLS["element"], y), element, fontname="helv", fontsize=8, color=rgb(INK))
    _chip(page, COLS["statut"], y, finding["statut"])
    page.insert_text((COLS["ecart"], y), _gap_text(finding), fontname="helv", fontsize=7.4, color=rgb(TEXT))
    for side in ("plan", "atelier"):
        mark = marks.get((k, side))
        if mark:
            _page_link(page, side, y, mark)


def draw_index(out: fitz.Document, gaps: list[dict], marks: dict, project: str, n_index: int) -> None:
    logo = logo_pdf()
    for i in range(n_index):
        rows_here = min(INDEX_LINES_PER_PAGE, len(gaps) - i * INDEX_LINES_PER_PAGE)
        _index_frame(out[i], project, logo, max(rows_here, 1))
    for k, finding in enumerate(gaps):
        _index_row(out[k // INDEX_LINES_PER_PAGE], k, finding, marks)
    if logo is not None:
        logo.close()
