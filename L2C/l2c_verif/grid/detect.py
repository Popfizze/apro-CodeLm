from __future__ import annotations

from statistics import median

from .model import RE_LET, RE_NUM, Grid, GridLine, grid_label

EDGE_TOLERANCE = 10.0
SIZE_TOLERANCE = 0.15


def cluster(values: list[tuple], tol: float) -> list[list]:
    groups: list[list[tuple]] = []
    for value in sorted(values, key=lambda v: v[0]):
        if groups and value[0] - groups[-1][-1][0] <= tol:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [[d for _, d in g] for g in groups]


def _mode_band(values: list[float], tol: float = 8.0) -> float:
    groups = cluster([(v, {"v": v}) for v in values], tol)
    return median(d["v"] for d in max(groups, key=len))


def _span_bands(members: list[dict], pos_key: str, span_key: str) -> tuple[float, float]:
    spans: dict[tuple, list[float]] = {}
    for c in members:
        spans.setdefault((c["text"], round(c[pos_key])), []).append(c[span_key])
    return _mode_band([min(v) for v in spans.values()]), _mode_band([max(v) for v in spans.values()])


def _near(value: float, reference: float) -> bool:
    return abs(value - reference) <= EDGE_TOLERANCE


def _line_members(members: list[dict], line: GridLine, pos_key: str) -> list[dict]:
    return [c for c in members if c["text"] == line.label and abs(c[pos_key] - line.pos) < 4]


def _edge_filter(lines: list[GridLine], members: list[dict], pos_key: str, span_key: str):
    if len(lines) < 3:
        return lines, members
    low, high = _span_bands(members, pos_key, span_key)
    keep, keep_members = [], []
    for line in lines:
        spans = [c[span_key] for c in _line_members(members, line, pos_key)]
        if not spans or not (_near(min(spans), low) or _near(max(spans), high)):
            continue
        keep.append(line)
        keep_members.extend(
            c
            for c in _line_members(members, line, pos_key)
            if _near(c[span_key], low) or _near(c[span_key], high)
        )
    return keep, keep_members


def _candidates(lines: list[dict]) -> list[dict]:
    out = []
    for ln in lines:
        text = grid_label(ln["text"])
        if tuple(round(v) for v in ln.get("dir", (1, 0))) != (1, 0):
            continue
        if RE_NUM.match(text) or RE_LET.match(text):
            x0, y0, x1, y1 = ln["bbox"]
            out.append(
                {
                    "text": text,
                    "cx": (x0 + x1) / 2,
                    "cy": (y0 + y1) / 2,
                    "size": ln["size"],
                    "bbox": ln["bbox"],
                }
            )
    return out


def _paired_lines(candidates: list[dict], axis_key: str, span_key: str, min_sep: float, kind, tol: float):
    lines, members = [], []
    for group in cluster([(c[axis_key], c) for c in candidates if kind.match(c["text"])], tol):
        by_text: dict[str, list[dict]] = {}
        for c in group:
            by_text.setdefault(c["text"], []).append(c)
        for text, labels in by_text.items():
            spans = [c[span_key] for c in labels]
            if len(labels) >= 2 and max(spans) - min(spans) > min_sep:
                members.extend(labels)
                lines.append(GridLine(text, median(c[axis_key] for c in labels)))
    return lines, members


def _matches_paired(candidate: dict, kind, known: set[str], size: float) -> bool:
    if not kind.match(candidate["text"]) or candidate["text"] in known:
        return False
    return abs(candidate["size"] - size) < SIZE_TOLERANCE * size


def _add_unpaired(
    lines: list[GridLine], paired: list[dict], candidates: list[dict], kind, axis: tuple
) -> None:
    pos_key, band_key, band_tol = axis
    if not paired:
        return
    size = median(c["size"] for c in paired)
    bands = sorted({round(c[band_key]) for c in paired})
    known = {g.label for g in lines}
    for c in candidates:
        if _matches_paired(c, kind, known, size) and any(abs(c[band_key] - b) < band_tol for b in bands):
            lines.append(GridLine(c["text"], c[pos_key], paired=False))
            known.add(c["text"])


def detect_grid(lines: list[dict], page_w: float, page_h: float, tol: float = 3.0) -> Grid:
    candidates = _candidates(lines)
    v_num, m_vn = _paired_lines(candidates, "cx", "cy", page_h * 0.3, RE_NUM, tol)
    v_let, m_vl = _paired_lines(candidates, "cx", "cy", page_h * 0.3, RE_LET, tol)
    h_let, m_hl = _paired_lines(candidates, "cy", "cx", page_w * 0.3, RE_LET, tol)
    h_num, m_hn = _paired_lines(candidates, "cy", "cx", page_w * 0.3, RE_NUM, tol)
    grid = Grid(letters_vertical=len(v_let) + len(h_num) > len(v_num) + len(h_let))
    if grid.letters_vertical:
        verticals, horizontals, v_kind, h_kind = (v_let, m_vl), (h_num, m_hn), RE_LET, RE_NUM
    else:
        verticals, horizontals, v_kind, h_kind = (v_num, m_vn), (h_let, m_hl), RE_NUM, RE_LET
    grid.verticals, paired_v = _edge_filter(*verticals, "cx", "cy")
    grid.horizontals, paired_h = _edge_filter(*horizontals, "cy", "cx")
    _add_unpaired(grid.verticals, paired_v, candidates, v_kind, ("cx", "cy", 3))
    _add_unpaired(grid.horizontals, paired_h, candidates, h_kind, ("cy", "cx", 4))
    grid.verticals.sort(key=lambda g: g.pos)
    grid.horizontals.sort(key=lambda g: g.pos)
    return grid
