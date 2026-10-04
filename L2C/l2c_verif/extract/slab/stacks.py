from __future__ import annotations

import re

from ...geometry import center
from ...rebar import norm_text

RE_CALLOUT = re.compile(r"^(?:(\d{1,3})\s*\+\s*)?(\d{1,3})\s+(\d{2})(?:M\b|[A-Z]{1,3}\s?\d|\d{1,2}-\d{2})")
RE_PLUS = re.compile(r"^\d{1,3}\s*\+$")
RE_SUFFIX = re.compile(r"\+\s*(\d{1,3})\s+\d{2}(?:M\b|[A-Z]{1,3}\s?\d|\d{1,2}-\d{2})")
HORIZONTAL, UPWARD = (1, 0), (0, -1)


def is_callout(ln: dict) -> bool:
    return RE_CALLOUT.match(norm_text(ln["text"])) is not None


def line_quantity(text: str) -> int:
    t = norm_text(text)
    callout = RE_CALLOUT.match(t)
    revisions = sum(int(m.group(1)) for m in RE_SUFFIX.finditer(t[callout.end() :]))
    return int(callout.group(1) or 0) + int(callout.group(2)) + revisions


def _union(a, b) -> tuple:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _reading_gap(first: dict, second: dict, reference: dict) -> float | None:
    rx0, ry0, rx1, ry1 = reference["bbox"]
    if first["dir"] == HORIZONTAL:
        size = max(ry1 - ry0, 1.0)
        gap = second["bbox"][0] - first["bbox"][2]
        offset = abs(center(first["bbox"])[1] - center(second["bbox"])[1])
    elif first["dir"] == UPWARD:
        size = max(rx1 - rx0, 1.0)
        gap = first["bbox"][1] - second["bbox"][3]
        offset = abs(center(first["bbox"])[0] - center(second["bbox"])[0])
    else:
        return None
    return gap if offset <= 0.3 * size and -1 <= gap <= 2.5 * size else None


def _suffix_target(lines: list[dict], suffix: dict, used: set, merged: dict) -> tuple | None:
    best = None
    for original in lines:
        if original is suffix or id(original) in used:
            continue
        ln = merged.get(id(original), original)
        if ln["dir"] != suffix["dir"] or not is_callout(ln):
            continue
        gap = _reading_gap(ln, suffix, ln)
        if gap is not None and (best is None or gap < best[0]):
            best = (gap, ln, id(original))
    return best


def _suffix_order(ln: dict) -> float:
    return ln["bbox"][0] if ln["dir"] == HORIZONTAL else -ln["bbox"][3]


def merge_suffixes(lines: list[dict]) -> list[dict]:
    suffixes = [ln for ln in lines if RE_SUFFIX.match(norm_text(ln["text"]))]
    if not suffixes:
        return lines
    used, merged = set(), {}
    for suffix in sorted(suffixes, key=_suffix_order):
        best = _suffix_target(lines, suffix, used, merged)
        if best is None:
            continue
        _, ln, key = best
        merged[key] = {
            **ln,
            "bbox": _union(suffix["bbox"], ln["bbox"]),
            "bbox0": ln.get("bbox0", ln["bbox"]),
            "revised": True,
            "text": f"{ln['text']} {norm_text(suffix['text'])}",
        }
        used.add(id(suffix))
    return [merged.get(id(ln), ln) for ln in lines if id(ln) not in used]


def _prefix_target(lines: list[dict], prefix: dict, merged: dict) -> dict | None:
    best = None
    for ln in lines:
        if ln is prefix or ln["dir"] != prefix["dir"] or id(ln) in merged or not is_callout(ln):
            continue
        gap = _reading_gap(prefix, ln, ln)
        if gap is not None and (best is None or gap < best[0]):
            best = (gap, ln)
    return best[1] if best else None


def merge_prefixes(lines: list[dict]) -> list[dict]:
    prefixes = [ln for ln in lines if RE_PLUS.match(norm_text(ln["text"]))]
    if not prefixes:
        return lines
    used, merged = set(), {}
    for prefix in prefixes:
        ln = _prefix_target(lines, prefix, merged)
        if ln is None:
            continue
        merged[id(ln)] = {
            **ln,
            "bbox": _union(prefix["bbox"], ln["bbox"]),
            "bbox0": ln["bbox"],
            "text": f"{norm_text(prefix['text'])} {ln['text']}",
        }
        used.add(id(prefix))
    return [merged.get(id(ln), ln) for ln in lines if id(ln) not in used]


def starts(ln: dict) -> list[float]:
    boxes = [ln["bbox"]] + ([ln["bbox0"]] if "bbox0" in ln else [])
    if ln["dir"] == HORIZONTAL:
        return [b[0] for b in boxes]
    if ln["dir"] == UPWARD:
        return [b[3] for b in boxes]
    return [b[1] for b in boxes]


def stack_gap(current: dict, other: dict) -> tuple[float, float]:
    cx0, cy0, cx1, cy1 = current["bbox"]
    x0, _, x1, y1 = other["bbox"]
    if current["dir"] == HORIZONTAL:
        return max(cy1 - cy0, 1.0), cy0 - y1
    if current["dir"] == UPWARD:
        return max(cx1 - cx0, 1.0), cx0 - x1
    return max(cx1 - cx0, 1.0), x0 - cx1


def _stacked_gap(
    current: dict, ln: dict, current_starts: list[float], max_gap: float, align: float
) -> float | None:
    thickness, gap = stack_gap(current, ln)
    tolerance = max(3.0, align * thickness)
    aligned = any(abs(a - b) <= tolerance for a in starts(ln) for b in current_starts)
    return gap if aligned and -0.3 * thickness <= gap <= max_gap * thickness else None


def previous_line(
    lines: list[dict], current: dict, max_gap: float = 0.8, align: float = 0.6, exclude=frozenset()
):
    current_starts = starts(current)
    best = None
    for ln in lines:
        if ln is current or ln["dir"] != current["dir"] or id(ln) in exclude:
            continue
        gap = _stacked_gap(current, ln, current_starts, max_gap, align)
        if gap is not None and (best is None or gap < best[0]):
            best = (gap, ln)
    return best[1] if best else None


def tight(current: dict, previous: dict) -> bool:
    thickness, gap = stack_gap(current, previous)
    aligned = any(abs(a - b) <= 1.5 for a in starts(previous) for b in starts(current))
    return aligned and gap <= 0.35 * thickness
