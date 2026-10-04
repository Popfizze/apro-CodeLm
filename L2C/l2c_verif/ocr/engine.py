from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import fitz
import numpy as np

log = logging.getLogger("l2c_verif")

WINDOWS_DEFAULT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
DISABLED_VALUES = ("0", "off", "false", "no")
MIN_STROKE_PX_AT_300DPI = 3.0
TSV_COLUMNS = 12
WORD_LEVEL = "5"

_warned = False


def tesseract_cmd() -> str | None:
    global _warned
    if os.environ.get("L2C_OCR", "1").strip().lower() in DISABLED_VALUES:
        return None
    candidates = (
        os.environ.get("TESSERACT_CMD"),
        shutil.which("tesseract"),
        str(WINDOWS_DEFAULT) if WINDOWS_DEFAULT.is_file() else None,
    )
    found = next((c for c in candidates if c and Path(c).is_file()), None)
    if found is None and not _warned:
        log.warning(
            "Tesseract not found (set TESSERACT_CMD or add it to PATH): pages without text layer are skipped"
        )
        _warned = True
    return found


def available() -> bool:
    return tesseract_cmd() is not None


def _parse_tsv(output: bytes) -> list[dict]:
    words = []
    for row in output.decode("utf-8", "replace").splitlines()[1:]:
        f = row.split("\t")
        if len(f) != TSV_COLUMNS or f[0] != WORD_LEVEL or not f[11].strip():
            continue
        words.append(
            {
                "text": f[11].strip(),
                "conf": float(f[10]),
                "l": int(f[6]),
                "t": int(f[7]),
                "w": int(f[8]),
                "h": int(f[9]),
                "key": (int(f[2]), int(f[3]), int(f[4])),
            }
        )
    return words


def run_tesseract(img: np.ndarray, dpi: int, psm: int = 11, timeout: int = 900) -> list[dict]:
    cmd = tesseract_cmd()
    if cmd is None:
        return []
    img = np.ascontiguousarray(img)
    data = fitz.Pixmap(fitz.csGRAY, img.shape[1], img.shape[0], img.tobytes(), 0).tobytes("png")
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    args = [
        cmd,
        "stdin",
        "stdout",
        "--psm",
        str(psm),
        "--dpi",
        str(dpi),
        "-l",
        "eng",
        "-c",
        "tessedit_do_invert=0",
        "tsv",
    ]
    try:
        result = subprocess.run(
            args,
            input=data,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
            check=False,
            **options,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Tesseract failed: %s", exc)
        return []
    if result.returncode != 0:
        log.warning("Tesseract failed: %s", result.stderr[-300:].decode("utf-8", "replace"))
        return []
    return _parse_tsv(result.stdout)


def render(page: fitz.Page, zoom: float, clip: fitz.Rect | None = None) -> np.ndarray:
    fitz.TOOLS.set_graphics_min_line_width(MIN_STROKE_PX_AT_300DPI * zoom * 72 / 300)
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY, clip=clip, alpha=False)
    finally:
        fitz.TOOLS.set_graphics_min_line_width(0)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, : pix.width].copy()
