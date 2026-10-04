from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from pathlib import Path

import fitz

from ... import CACHE_DIR
from ...geometry import center
from ...ocr import RECIPE as OCR_RECIPE
from ...ocr import ocr_clip_lines
from .text import suspicious, worth_rereading

REREAD_CACHE = CACHE_DIR / "ocr"
REREAD_DPI = 450


def center_inside(ln: dict, other: dict) -> bool:
    x0, y0, x1, y1 = other["bbox"]
    cx, cy = center(ln["bbox"])
    return x0 <= cx <= x1 and y0 <= cy <= y1


def _cache_file(page) -> Path:
    st = Path(page.path).stat()
    raw = f"tess-reread4|{OCR_RECIPE}|{page.fichier}|{page.page}|{st.st_size}|{st.st_mtime_ns}"
    key = hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:16]
    return REREAD_CACHE / f"{Path(page.fichier).stem}_p{page.page}_{key}.json"


def _load(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        lines = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return [{**ln, "bbox": tuple(ln["bbox"]), "dir": tuple(ln["dir"])} for ln in lines]


def _save(path: Path, lines: list[dict]) -> None:
    with suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")


def _reread_line(page: fitz.Page, line: dict) -> list[dict]:
    x0, y0, x1, y1 = line["bbox"]
    h = max(y1 - y0, 1.0)
    clip = fitz.Rect(x0 - 5 * h, y0 - 0.3 * h, x1 + h, y1 + 0.3 * h)
    reread = [r for r in ocr_clip_lines(page, clip, dpi=REREAD_DPI) if center_inside(line, r)]
    if not reread or any(suspicious(r["text"]) for r in reread):
        return []
    return reread


def _rereads(page_ref, lines: list[dict]) -> tuple[set[int], list[dict]]:
    targets = [i for i, ln in enumerate(lines) if ln["dir"] == (1, 0) and worth_rereading(ln["text"])]
    replaced, added = set(), []
    if not targets:
        return replaced, added
    with fitz.open(page_ref.path) as doc:
        page = doc[page_ref.page - 1]
        for i in targets:
            reread = _reread_line(page, lines[i])
            if reread:
                replaced.add(i)
            for r in reread:
                if not any(center_inside(r, a) for a in added):
                    added.append(r)
    return replaced, added


def reread_lines(page_ref) -> list[dict]:
    path = _cache_file(page_ref)
    cached = _load(path)
    if cached is not None:
        return cached
    lines = [dict(ln) for ln in page_ref.lines]
    replaced, added = _rereads(page_ref, lines)
    for r in added:
        replaced.update(k for k, ln in enumerate(lines) if ln["dir"] == (1, 0) and center_inside(ln, r))
    lines = [ln for k, ln in enumerate(lines) if k not in replaced] + added
    _save(path, lines)
    return lines
