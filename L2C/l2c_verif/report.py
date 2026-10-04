from __future__ import annotations

import argparse
import io
from pathlib import Path

import fitz

from .annex_a import export_annex_a
from .annotate import build_annotated_pdfs
from .report_html import Decorations, build_html
from .style import BORDER, BORDER_SOFT, CYAN, INK, LOGO_SVG, TEXT, rgb

REPORT_FILE = "report.pdf"
PAGE_RECT = fitz.paper_rect("letter")
MARGIN = 42
FOOTER_H = 24
MIN_BOX_SIZE = 0.5

CSS = f"""
* {{ font-family: sans-serif; }}
body {{ color: {TEXT}; font-size: 8.5pt; }}
p.logo {{ margin: 0 0 8pt 0; }}
h1 {{ font-size: 12.5pt; color: {INK}; font-weight: normal; margin: 0 0 14pt 0; padding-bottom: 7pt;
      border-bottom: 1.5px solid {CYAN}; }}
h2 {{ font-size: 9.5pt; color: {INK}; font-weight: bold; margin: 18pt 0 9pt 0; }}
h3 {{ font-size: 9pt; color: {INK}; font-weight: bold; margin: 16pt 0 2pt 0; padding-bottom: 4pt;
      border-bottom: 1px solid {CYAN}; }}
table {{ border-collapse: collapse; width: 100%; }}
th {{ color: {TEXT}; font-weight: bold; font-size: 6.8pt; text-align: left; padding: 6pt 8pt 5pt 8pt;
      border-bottom: 1px solid {CYAN}; }}
td {{ color: {TEXT}; font-size: 8.2pt; padding: 4.5pt 8pt; border-bottom: 0.5px solid {BORDER_SOFT}; }}
td.num, th.num {{ text-align: right; }}
td.sheet, td.tot {{ color: {INK}; font-weight: bold; }}
.finding {{ margin: 12pt 0 0 0; }}
p.fhead {{ font-size: 9.5pt; font-weight: bold; color: {INK}; margin: 0; padding: 7pt 10pt 3pt 10pt; }}
p.meta {{ color: {TEXT}; font-size: 8.2pt; margin: 0; padding: 1pt 10pt; }}
p.last {{ padding-bottom: 7pt; margin-bottom: 6pt; }}
p.note {{ color: {TEXT}; font-size: 8.2pt; margin: 4pt 0 0 0; padding: 0 10pt; }}
.lbl {{ color: {INK}; font-weight: bold; }}
.chip {{ font-size: 6.8pt; font-weight: bold; }}
"""


def _logo_archive() -> fitz.Archive | None:
    try:
        svg = LOGO_SVG.read_text(encoding="utf-8").replace("currentColor", INK)
    except OSError:
        return None
    archive = fitz.Archive()
    archive.add(svg.encode("utf-8"), "logo.svg")
    return archive


def _render(html_text: str, archive: fitz.Archive | None) -> tuple[bytes, dict]:
    story = fitz.Story(html=html_text, user_css=CSS, archive=archive)
    where = fitz.Rect(MARGIN, MARGIN, PAGE_RECT.width - MARGIN, PAGE_RECT.height - MARGIN - FOOTER_H)
    boxes: dict[tuple[int, str], list[fitz.Rect]] = {}
    page_index = 0

    def record(position) -> None:
        if not position.id or not position.id.startswith("deco"):
            return
        rect = fitz.Rect(position.rect)
        if rect.width > MIN_BOX_SIZE and rect.height > MIN_BOX_SIZE:
            boxes.setdefault((page_index, position.id.rsplit("-", 1)[0]), []).append(rect)

    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    more = 1
    while more:
        device = writer.begin_page(PAGE_RECT)
        more, _ = story.place(where)
        story.element_positions(record)
        story.draw(device)
        writer.end_page()
        page_index += 1
    writer.close()
    return buffer.getvalue(), boxes


def _decoration_rect(rects: list[fitz.Rect], style: dict) -> fitz.Rect:
    rect = fitz.Rect(rects[0])
    for other in rects[1:]:
        rect |= other
    px, py = style["pad"]
    if style["full"]:
        rect = fitz.Rect(MARGIN, rect.y0, PAGE_RECT.width - MARGIN, rect.y1)
    return fitz.Rect(rect.x0 - px, rect.y0 - py, rect.x1 + px, rect.y1 + py)


def _draw_box(page: fitz.Page, rect: fitz.Rect, style: dict) -> None:
    radius = (min(0.5, style["radius"] / rect.width), min(0.5, style["radius"] / rect.height))
    page.draw_rect(
        rect,
        color=rgb(style["stroke"]) if style["stroke"] else None,
        fill=rgb(style["fill"]) if style["fill"] else None,
        width=0.8 if style["stroke"] else 0,
        radius=radius,
        overlay=False,
    )


def _draw_decorations(doc: fitz.Document, boxes: dict, deco: Decorations) -> None:
    items = sorted(boxes.items(), key=lambda kv: deco.styles.get(kv[0][1], {}).get("layer", 9))
    for (page_index, group), rects in items:
        style = deco.styles.get(group)
        if not style or page_index >= doc.page_count:
            continue
        rect = _decoration_rect(rects, style)
        if not rect.is_empty:
            _draw_box(doc[page_index], rect, style)


def _add_footer(doc: fitz.Document) -> None:
    total = doc.page_count
    for number, page in enumerate(doc, start=1):
        y = page.rect.height - MARGIN + 6
        page.draw_line((MARGIN, y - 12), (page.rect.width - MARGIN, y - 12), color=rgb(BORDER), width=0.6)
        text = f"Page {number} / {total}"
        width = fitz.get_text_length(text, fontname="helv", fontsize=7.5)
        page.insert_text(
            (page.rect.width - MARGIN - width, y), text, fontname="helv", fontsize=7.5, color=rgb(TEXT)
        )


def build_report(out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = _logo_archive()
    html_text, deco = build_html(out_dir, with_logo=archive is not None)
    pdf_bytes, boxes = _render(html_text, archive)
    doc = fitz.open("pdf", pdf_bytes)
    _draw_decorations(doc, boxes, deco)
    _add_footer(doc)
    path = out_dir / REPORT_FILE
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m l2c_verif.report")
    parser.add_argument("out_dir", type=Path, help="results/<PROJET> directory")
    parser.add_argument(
        "--data", type=Path, default=None, help="data/<PROJET> directory (source PDFs) for annotated.pdf"
    )
    args = parser.parse_args(argv)
    print(build_report(args.out_dir))
    for path in export_annex_a(args.out_dir):
        print(path)
    if args.data is not None:
        for path in build_annotated_pdfs(args.out_dir, args.data):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
