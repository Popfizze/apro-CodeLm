from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import suppress
from pathlib import Path

import fitz

from .. import CACHE_DIR as CACHE_ROOT
from .engine import available
from .reader import DPI, RECIPE, ocr_page
from .text import fix_role_label, fix_text

log = logging.getLogger("l2c_verif")

CACHE_DIR = CACHE_ROOT / "ocr_tess"
MIN_TEXT_CHARS = 20
RE_ALNUM = re.compile(r"[A-Za-z0-9]")

_SHA: dict[tuple, str] = {}


def page_has_text_layer(page: fitz.Page, min_chars: int = MIN_TEXT_CHARS) -> bool:
    return len(RE_ALNUM.findall(page.get_text("text"))) >= min_chars


def _file_sha(path: Path) -> str:
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _SHA:
        _SHA[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _SHA[key]


def _cache_file(pdf: Path, page_index: int, dpi: int, cache_dir: Path) -> Path:
    raw = f"{RECIPE}|{dpi}|{_file_sha(pdf)}|{page_index}"
    key = hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:16]
    return Path(cache_dir) / f"{pdf.stem}_p{page_index + 1}_{key}.json"


def _restore(block: dict) -> None:
    block["bbox"] = tuple(block["bbox"])
    for line in block["lines"]:
        line["bbox"], line["dir"] = tuple(line["bbox"]), tuple(line["dir"])
        for span in line["spans"]:
            span["bbox"], span["origin"] = tuple(span["bbox"]), tuple(span["origin"])
            span["text"] = fix_role_label(fix_text(span["text"]))


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for block in data.get("blocks", []):
        _restore(block)
    return data


def _store(path: Path, data: dict) -> None:
    with suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def ocr_page_dict(page: fitz.Page, cache_dir: Path | None = None) -> dict:
    empty = {"width": page.rect.width, "height": page.rect.height, "blocks": []}
    if not available():
        return empty
    pdf = Path(page.parent.name)
    path = _cache_file(pdf, page.number, DPI, cache_dir or CACHE_DIR) if pdf.is_file() else None
    cached = _load(path) if path is not None and path.exists() else None
    if cached is not None:
        return cached
    try:
        data = ocr_page(page, DPI)
    except Exception as exc:
        log.warning("OCR failed on %s p%d: %s", pdf.name, page.number + 1, exc)
        return empty
    if path is None:
        return data
    _store(path, data)
    return _load(path) if path.exists() else data


def _ocr_job(
    pdf: str, page_index: int, dpi: int, cache_file: str, threads: int
) -> tuple[str, int, float, int]:
    with fitz.open(pdf) as doc:
        data = ocr_page(doc[page_index], dpi, threads)
    path = Path(cache_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return pdf, page_index, data["ocr"]["seconds"], len(data["blocks"])


def _pending_jobs(pdfs: Iterable[Path]) -> list[tuple]:
    jobs = []
    for pdf in map(Path, pdfs):
        with fitz.open(pdf) as doc:
            for i, page in enumerate(doc):
                path = _cache_file(pdf, i, DPI, CACHE_DIR) if not page_has_text_layer(page) else None
                if path is not None and not path.exists():
                    jobs.append((str(pdf), i, DPI, str(path)))
    return jobs


def _finished(future) -> int:
    try:
        pdf, page_index, seconds, n = future.result()
    except Exception as exc:
        log.warning("OCR job failed: %s", exc)
        return 0
    log.debug("OCR %s p%d: %d lines in %.1fs", Path(pdf).name, page_index + 1, n, seconds)
    return 1


def _run_jobs(jobs: list[tuple], workers: int, threads: int) -> int:
    done = 0
    try:
        with ProcessPoolExecutor(workers) as executor:
            futures = [executor.submit(_ocr_job, *job, threads) for job in jobs]
            for future in as_completed(futures):
                done += _finished(future)
    except Exception as exc:
        log.warning("OCR prefetch unavailable (%s): falling back to page-by-page OCR", exc)
    return done


def prefetch(pdfs: Iterable[Path]) -> int:
    if not available():
        return 0
    jobs = _pending_jobs(pdfs)
    if not jobs:
        return 0
    cpu = os.cpu_count() or 2
    workers = max(1, min(len(jobs), cpu // 3))
    threads = max(2, cpu // workers)
    log.info(
        "OCR: %d page(s) without text layer, %d worker(s) x %d Tesseract thread(s)",
        len(jobs),
        workers,
        threads,
    )
    started = time.time()
    done = _run_jobs(jobs, workers, threads)
    log.info("OCR: %d page(s) in %.1fs", done, time.time() - started)
    return done
