from __future__ import annotations

import json
import math
from pathlib import Path

import fitz

from .annotate_index import INDEX_LINES_PER_PAGE, INDEX_RECT, draw_index, gap_summary, link, rect_radius
from .style import (
    GAP_STATUSES,
    STATUS_COLORS,
    STATUS_LABEL,
    by_id,
    load_json,
    load_records,
    natural_key,
    rgb,
    sheet_key,
)

OUT_FILE = "annotated.pdf"
TAG = "annotate"
LABEL_SLOTS = 12
SIDES = ("plan", "atelier")


class _Resolver:
    def __init__(self, data_root: Path):
        self.root = Path(data_root)
        self.by_name: dict[str, Path] | None = None
        self.docs: dict[Path, fitz.Document] = {}

    def path(self, fichier: str | None) -> Path | None:
        if not fichier:
            return None
        direct = self.root / fichier
        if direct.is_file():
            return direct
        if self.by_name is None:
            self.by_name = {}
            for pdf in self.root.rglob("*.pdf"):
                self.by_name.setdefault(pdf.name.lower(), pdf)
        return self.by_name.get(Path(fichier).name.lower())

    def doc(self, path: Path) -> fitz.Document:
        if path not in self.docs:
            self.docs[path] = fitz.open(path)
        return self.docs[path]

    def close(self) -> None:
        for doc in self.docs.values():
            doc.close()


def _color(finding: dict) -> tuple[float, float, float]:
    return rgb(STATUS_COLORS[finding["statut"]][0])


def _item_rect(item: dict, page: fitz.Page) -> fitz.Rect:
    bb = item.get("bbox")
    if isinstance(bb, list | tuple) and len(bb) == 4 and bb[2] > bb[0] and bb[3] > bb[1]:
        rect = fitz.Rect(bb)
    else:
        x, y = float(item.get("x") or 0), float(item.get("y") or 0)
        rect = fitz.Rect(x - 30, y - 15, x + 30, y + 15)
    unrotated = fitz.Rect(0, 0, page.cropbox.width, page.cropbox.height)
    if page.rotation and not unrotated.contains(rect) and page.rect.contains(rect):
        rect = rect * page.derotation_matrix
    return rect


def _ellipse(rect: fitz.Rect, page: fitz.Page) -> fitz.Rect:
    pad = max(12.0, 0.25 * max(rect.width, rect.height))
    ellipse = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)
    inside = ellipse & fitz.Rect(0, 0, page.cropbox.width, page.cropbox.height)
    return ellipse if inside.is_empty else inside


def _short_gap(finding: dict) -> str:
    ecarts = finding.get("ecarts") or []
    if not ecarts:
        return STATUS_LABEL.get(finding.get("statut"), "").lower()
    more = f" (+{len(ecarts) - 1})" if len(ecarts) > 1 else ""
    return f"{gap_summary(ecarts[0])}{more}".strip()


def _scale(page: fitz.Page) -> float:
    return max(page.cropbox.width, page.cropbox.height) / 1000.0


def _draw_circle(page: fitz.Page, rect: fitz.Rect, color) -> fitz.Rect:
    ellipse = _ellipse(rect, page)
    page.draw_oval(ellipse, color=color, width=max(2.0, 2.2 * _scale(page)))
    return ellipse


def _label_box(x: float, y: float, width: float, size: float) -> fitz.Rect:
    return fitz.Rect(x - 2, y - size, x + width + 2, y + size * 0.3)


def _place_label(
    visual: fitz.Rect, bounds: fitz.Rect, width: float, size: float, placed: list
) -> tuple[fitz.Rect, int]:
    step = size * 1.5
    candidates = []
    for k in range(LABEL_SLOTS):
        candidates.append((visual.x0, visual.y0 - size * 0.5 - k * step))
        candidates.append((visual.x0, visual.y1 + size * 1.2 + k * step))
    for index, (x, y) in enumerate(candidates):
        box = _label_box(min(max(x, 2), bounds.width - width - 4), y, width, size)
        if box.y0 >= 0 and box.y1 <= bounds.height and not any(box.intersects(p) for p in placed):
            return box, index
    return _label_box(*candidates[0], width, size), 0


def _draw_leader(page: fitz.Page, box: fitz.Rect, visual: fitz.Rect, color, scale: float) -> None:
    above = box.y1 <= visual.y0
    start = fitz.Point(box.x0 + 4, box.y1 if above else box.y0)
    end = fitz.Point((visual.x0 + visual.x1) / 2, visual.y0 if above else visual.y1)
    page.draw_line(
        start * page.derotation_matrix, end * page.derotation_matrix, color=color, width=max(0.5, 0.4 * scale)
    )


def _draw_label(page: fitz.Page, ellipse: fitz.Rect, color, label: str, placed: list[fitz.Rect]) -> None:
    scale = _scale(page)
    size = max(6.0, 5.5 * scale)
    width = fitz.get_text_length(label, fontname="helv", fontsize=size)
    visual = ellipse * page.rotation_matrix
    box, index = _place_label(visual, page.rect, width, size, placed)
    placed.append(box)
    if index >= 2:
        _draw_leader(page, box, visual, color, scale)
    radius = rect_radius(box, size * 0.45)
    page.draw_rect(
        box * page.derotation_matrix,
        color=color,
        fill=(1, 1, 1),
        width=max(0.6, 0.5 * scale),
        fill_opacity=0.9,
        radius=radius,
    )
    origin = fitz.Point(box.x0 + 2, box.y1 - size * 0.3) * page.derotation_matrix
    page.insert_text(origin, label, fontname="helv", fontsize=size, color=color, rotate=page.rotation)


def _source_page(resolver: _Resolver, item: dict | None) -> tuple[Path, int] | None:
    if not item:
        return None
    path, page_no = resolver.path(item.get("fichier")), item.get("page")
    if path is None or not isinstance(page_no, int) or not 1 <= page_no <= resolver.doc(path).page_count:
        return None
    return path, page_no


def _locate(gaps: list[dict], items: dict[str, dict], resolver: _Resolver) -> dict[str, list]:
    sides: dict[str, list] = {side: [] for side in SIDES}
    for k, finding in enumerate(gaps):
        for side in SIDES:
            item = items[side].get(finding.get(f"{side}_item"))
            source = _source_page(resolver, item)
            if source is not None:
                sides[side].append((k, item, source))
    return sides


def _page_order(sides: dict[str, list]) -> list[tuple[Path, int]]:
    keys: list[tuple[Path, int]] = []
    for side in SIDES:
        for key in sorted({e[2] for e in sides[side]}, key=lambda t: (natural_key(t[0].name), t[1])):
            if key not in keys:
                keys.append(key)
    return keys


def _assemble(
    gaps: list[dict], sides: dict[str, list], resolver: _Resolver
) -> tuple[fitz.Document, dict, int]:
    out = fitz.open()
    n_index = max(1, math.ceil(len(gaps) / INDEX_LINES_PER_PAGE))
    for _ in range(n_index):
        out.new_page(width=INDEX_RECT.width, height=INDEX_RECT.height)
    page_of: dict[tuple[Path, int], int] = {}
    for path, page_no in _page_order(sides):
        out.insert_pdf(
            resolver.doc(path), from_page=page_no - 1, to_page=page_no - 1, links=False, annots=False
        )
        page_of[(path, page_no)] = out.page_count - 1
    return out, page_of, n_index


def _draw_marks(out: fitz.Document, gaps: list[dict], sides: dict[str, list], page_of: dict) -> dict:
    marks: dict[tuple[int, str], tuple[int, fitz.Rect]] = {}
    for side in SIDES:
        for k, item, key in sides[side]:
            index = page_of[key]
            marks[(k, side)] = (
                index,
                _draw_circle(out[index], _item_rect(item, out[index]), _color(gaps[k])),
            )
    placed: dict[int, list[fitz.Rect]] = {}
    for (k, _), (index, ellipse) in marks.items():
        finding = gaps[k]
        label = f"{finding.get('element') or '?'} : {_short_gap(finding)}"
        _draw_label(out[index], ellipse, _color(finding), label, placed.setdefault(index, []))
    return marks


def _link_marks(out: fitz.Document, marks: dict) -> None:
    for (k, side), (index, ellipse) in marks.items():
        other = marks.get((k, "atelier" if side == "plan" else "plan"))
        if other:
            link(out[index], ellipse, other[0], fitz.Point(other[1].x0, other[1].y0))
        else:
            link(out[index], ellipse, k // INDEX_LINES_PER_PAGE)


def _sorted_gaps(findings: list) -> list[dict]:
    order = {s: i for i, s in enumerate(GAP_STATUSES)}
    gaps = [f for f in findings if isinstance(f, dict) and f.get("statut") in order]
    return sorted(
        gaps, key=lambda f: (sheet_key(f.get("feuillet")), order[f["statut"]], natural_key(f.get("element")))
    )


def _record_pages(findings_path: Path, findings: list, gaps: list[dict], marks: dict) -> None:
    for k, finding in enumerate(gaps):
        finding["annotated_pages"] = {
            side: (marks[(k, side)][0] + 1 if (k, side) in marks else None) for side in SIDES
        }
    findings_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")


def build_annotated_pdfs(out_dir: Path, data_root: Path) -> list[Path]:
    out_dir, data_root = Path(out_dir), Path(data_root)
    findings_path = out_dir / "findings.json"
    findings = load_json(findings_path, [], TAG)
    items = {
        "plan": by_id(load_records(out_dir / "items_plan.json", TAG)),
        "atelier": by_id(load_records(out_dir / "items_atelier.json", TAG)),
    }
    project = load_json(out_dir / "summary.json", {}, TAG).get("projet") or out_dir.name
    gaps = _sorted_gaps(findings)
    resolver = _Resolver(data_root)
    sides = _locate(gaps, items, resolver)
    out, page_of, n_index = _assemble(gaps, sides, resolver)
    resolver.close()
    marks = _draw_marks(out, gaps, sides, page_of)
    _link_marks(out, marks)
    draw_index(out, gaps, marks, project, n_index)
    path = out_dir / OUT_FILE
    out.save(path, garbage=3, deflate=True)
    out.close()
    if gaps:
        _record_pages(findings_path, findings, gaps, marks)
    return [path]
