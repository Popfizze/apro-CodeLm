from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import fitz
import numpy as np

from .engine import available, render, run_tesseract
from .image import erase_long_lines, tiles
from .lines import FONT_ASCENT, FONT_DESCENT, dedupe, pass_lines, to_visual

RECIPE = "v6"
DPI = 300
TESSERACT_MAX_SIDE_PX = 30000
LONG_LINE_MIN_PT = 24.0


def _tile_words(images: list[tuple], jobs: list[tuple], index: int, dpi: int, psm: int) -> list[dict]:
    image_index, (y0, x0, y1, x1) = jobs[index]
    words = run_tesseract(images[image_index][0][y0:y1, x0:x1], dpi, psm)
    for word in words:
        word["l"] += x0
        word["t"] += y0
        word["key"] = (index, *word["key"])
    return words


def _recognise(
    images: list[tuple], jobs: list[tuple], dpi: int, psm: int, threads: int | None
) -> list[list[dict]]:
    workers = max(1, min(threads or os.cpu_count() or 2, len(jobs)))
    with ThreadPoolExecutor(workers) as executor:
        return list(executor.map(lambda j: _tile_words(images, jobs, j, dpi, psm), range(len(jobs))))


def _image_words(jobs: list[tuple], results: list[list[dict]], image_index: int) -> list[dict]:
    return [
        w
        for (job_image, _), found in zip(jobs, results, strict=True)
        if job_image == image_index
        for w in found
    ]


def read_image(
    gray: np.ndarray,
    zoom: float,
    dpi: int,
    origin=(0.0, 0.0),
    vertical: bool = True,
    psm: int = 11,
    threads: int | None = None,
) -> list[dict]:
    gray, horizontal_rules, vertical_rules = erase_long_lines(gray, max(20, int(LONG_LINE_MIN_PT * zoom)))
    images = [(gray, False), (np.rot90(gray, -1), True)] if vertical else [(gray, False)]
    rules_across_text = [vertical_rules, np.rot90(horizontal_rules, -1)] if vertical else [vertical_rules]
    jobs = [(p, box) for p, (img, _) in enumerate(images) for box in tiles(img, zoom)]
    if not jobs:
        return []
    results = _recognise(images, jobs, dpi, psm, threads)
    lines = []
    for p, (_, rotated) in enumerate(images):
        words = _image_words(jobs, results, p)
        lines += [
            to_visual(ln, zoom, rotated, gray.shape[0], origin)
            for ln in pass_lines(words, rules_across_text[p])
        ]
    return dedupe(lines)


def _zoom(page: fitz.Page, dpi: int) -> float:
    return min(dpi / 72.0, TESSERACT_MAX_SIDE_PX / max(page.rect.width, page.rect.height))


def _span(ln: dict, matrix, bbox: tuple) -> dict:
    origin = fitz.Point(ln["origin"]) * matrix
    return {
        "size": round(ln["size"], 2),
        "flags": 0,
        "font": "OCR",
        "color": 0,
        "ascender": FONT_ASCENT,
        "descender": -FONT_DESCENT,
        "text": ln["text"],
        "origin": (round(origin.x, 2), round(origin.y, 2)),
        "bbox": bbox,
    }


def _to_dict(page: fitz.Page, lines: list[dict], meta: dict) -> dict:
    matrix = page.derotation_matrix
    zero = fitz.Point(0, 0) * matrix
    blocks = []
    for i, ln in enumerate(sorted(lines, key=lambda line: (round(line["bbox"][1]), line["bbox"][0]))):
        bbox = tuple(round(v, 2) for v in fitz.Rect(ln["bbox"]) * matrix)
        tip = fitz.Point(ln["dir"]) * matrix
        direction = (round(tip.x - zero.x), round(tip.y - zero.y))
        line = {
            "spans": [_span(ln, matrix, bbox)],
            "wmode": 0,
            "dir": direction,
            "bbox": bbox,
            "ocr_conf": ln["conf"],
        }
        blocks.append({"number": i, "type": 0, "bbox": bbox, "lines": [line]})
    return {"width": page.rect.width, "height": page.rect.height, "blocks": blocks, "ocr": meta}


def ocr_page(page: fitz.Page, dpi: int, threads: int | None = None) -> dict:
    started = time.time()
    zoom = _zoom(page, dpi)
    lines = read_image(render(page, zoom), zoom, dpi, threads=threads)
    meta = {"engine": "tesseract", "recipe": RECIPE, "dpi": dpi, "seconds": round(time.time() - started, 1)}
    return _to_dict(page, lines, meta)


def ocr_clip_lines(page: fitz.Page, clip: fitz.Rect, dpi: int = 450, psm: int = 6) -> list[dict]:
    if not available():
        return []
    zoom = dpi / 72.0
    clip = fitz.Rect(clip) & page.rect
    if clip.is_empty:
        return []
    lines = read_image(
        render(page, zoom, clip), zoom, dpi, origin=(clip.x0, clip.y0), vertical=False, psm=psm
    )
    return [
        {
            "text": ln["text"],
            "bbox": tuple(round(v, 1) for v in ln["bbox"]),
            "size": round(ln["size"], 1),
            "dir": (1, 0),
            "ocr": True,
        }
        for ln in lines
    ]
