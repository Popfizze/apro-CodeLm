from __future__ import annotations

import re
from functools import lru_cache
from itertools import pairwise

from ...geometry import lines_bbox, union_bbox
from ...leaders import page_drawings
from ...rebar import BAR_SIZES, norm_text
from .stacks import (
    RE_CALLOUT,
    is_callout,
    line_quantity,
    merge_prefixes,
    merge_suffixes,
    previous_line,
    tight,
)

RE_NM = re.compile(r"^(\d{1,2})\s*\(\s*(\d{1,2})\s*\)\s*(?:-\s*(\d{2})\s*M)?$")
RE_MB = re.compile(r"^(\d{1,2})\s*M\.?\s*B\.?$")
RE_ADD = re.compile(r"\bADD\b")
LOOSE_GAP = 2.5
MAX_STACK = 6
MAX_ORPHANS = 4


def box_gap(a, b) -> float:
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return (dx * dx + dy * dy) ** 0.5


def _axis(ln: dict) -> str:
    return "H" if tuple(ln["dir"]) == (1, 0) else "V"


@lru_cache(maxsize=128)
def _clouds(path: str, page_no: int) -> tuple:
    out = []
    for drawing in page_drawings(path, page_no):
        if drawing["type"] not in ("s", "fs"):
            continue
        x0, y0, x1, y1 = drawing["rect"]
        if sum(1 for item in drawing["items"] if item[0] == "c") >= 16 and max(x1 - x0, y1 - y0) >= 15:
            out.append((x0, y0, x1, y1))
    return tuple(out)


def plan_annotations(page) -> list[dict]:
    out = []
    for ln in page.lines:
        text = norm_text(ln["text"])
        match = RE_NM.match(text)
        if not match:
            continue
        size = f"{match.group(3)}M" if match.group(3) else None
        n = int(match.group(1))
        out.append(
            {
                "n": n,
                "n_alts": [n],
                "m": int(match.group(2)),
                "size": size if size in BAR_SIZES else None,
                "axis": _axis(ln),
                "bbox": ln["bbox"],
                "text": text,
                "amb": [],
            }
        )
    return out


def _is_added_bar(ln: dict) -> bool:
    return RE_ADD.search(norm_text(ln["text"])) is not None


def _stack_above(lines: list[dict], label: dict) -> list[dict]:
    stack, current = [], label
    for _ in range(MAX_STACK):
        previous = previous_line(lines, current)
        if previous is None or not is_callout(previous):
            break
        stack.append(previous)
        current = previous
    return stack


def _doubts(label: dict, stack: list[dict], counted: list[dict], bbox: list[float], clouds) -> list[str]:
    doubts = []
    if len(counted) < len(stack):
        doubts.append("ADD. bars in the stack")
    if any("bbox0" in s for s in stack):
        doubts.append("revision count (N + / + N) in the stack")
    if not all(tight(a, b) for a, b in pairwise([label, *stack])):
        doubts.append("loosely stacked lines")
    if any(box_gap(bbox, c) <= 2.0 for c in clouds):
        doubts.append("revision cloud around the stack")
    return doubts


def _thickness(ln: dict) -> float:
    if ln["dir"] == (1, 0):
        return ln["bbox"][3] - ln["bbox"][1]
    return ln["bbox"][2] - ln["bbox"][0]


def _stack_annotation(lines: list[dict], label: dict, bundles: str, clouds) -> dict | None:
    stack = _stack_above(lines, label)
    counted = [s for s in stack if not _is_added_bar(s)]
    if not counted:
        return None
    totals, total = [], 0
    for ln in counted:
        total += line_quantity(ln["text"])
        totals.append(total)
    sizes = {f"{RE_CALLOUT.match(norm_text(s['text'])).group(3)}M" for s in counted}
    members = [*stack, label]
    bbox = lines_bbox(members)
    text = " / ".join(norm_text(s["text"]) for s in [*reversed(stack), label])
    return {
        "n": total,
        "n_alts": totals,
        "m": int(bundles),
        "size": next(iter(sizes)) if len(sizes) == 1 else None,
        "axis": _axis(label),
        "bbox": bbox,
        "abox": union_bbox(s.get("bbox0", s["bbox"]) for s in members),
        "amb": _doubts(label, stack, counted, bbox, clouds),
        "lines": members,
        "t": _thickness(label),
        "text": f"{text} => {total}({bundles})",
    }


def _orphans(lines: list[dict], annotation: dict, used: set) -> list[dict]:
    members = annotation["lines"]
    current = members[-2] if len(members) > 1 else members[-1]
    extra = []
    for _ in range(MAX_ORPHANS):
        previous = previous_line(lines, current, max_gap=LOOSE_GAP, align=1.0, exclude=used)
        if previous is None or not is_callout(previous) or _is_added_bar(previous):
            break
        used.add(id(previous))
        extra.append(previous)
        current = previous
    return extra


def _extend_with_orphans(lines: list[dict], annotations: list[dict]) -> None:
    used = {id(ln) for a in annotations for ln in a["lines"]}
    for annotation in annotations:
        total = annotation["n"]
        extra = _orphans(lines, annotation, used)
        for ln in extra:
            total += line_quantity(ln["text"])
            annotation["n_alts"].append(total)
        if extra:
            annotation["amb"].append("orphan callout lines next to the stack")
            orphan_text = " / ".join(norm_text(ln["text"]) for ln in reversed(extra))
            annotation["text"] += f" | {orphan_text} => {total}"
        del annotation["lines"]


def shop_annotations(page) -> list[dict]:
    lines = merge_suffixes(merge_prefixes(page.lines))
    clouds = _clouds(str(page.path), page.page) if getattr(page, "path", None) else ()
    out = []
    for ln in lines:
        match = RE_MB.match(norm_text(ln["text"]))
        annotation = _stack_annotation(lines, ln, match.group(1), clouds) if match else None
        if annotation is not None:
            out.append(annotation)
    _extend_with_orphans(lines, out)
    for a in out:
        if any(
            b is not a and b["axis"] == a["axis"] and box_gap(a["bbox"], b["bbox"]) <= 1.5 * a["t"]
            for b in out
        ):
            a["amb"].append("another M.B. stack adjacent")
    return out
