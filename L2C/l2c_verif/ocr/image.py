from __future__ import annotations

import numpy as np

DARK_INK_LEVEL = 128
TILE_CORE_PT = 576.0
TILE_OVERLAP_PT = 144.0
MIN_TILE_INK = 50
STRIP = 768


def _long_run_mask(dark: np.ndarray, n_min: int) -> np.ndarray:
    rows, n = dark.shape
    if n < n_min:
        return np.zeros_like(dark)
    c = np.zeros((rows, n + 1), np.int32)
    np.cumsum(dark, axis=1, out=c[:, 1:])
    start = np.zeros((rows, n), np.bool_)
    start[:, : n - n_min + 1] = (c[:, n_min:] - c[:, :-n_min]) == n_min
    s = np.zeros((rows, n + 1), np.int32)
    np.cumsum(start, axis=1, out=s[:, 1:])
    lo = np.maximum(np.arange(n) - n_min + 1, 0)
    return (s[:, 1:] - s[:, lo]) > 0


def _thickened(mask: np.ndarray) -> np.ndarray:
    mask[1:] |= mask[:-1].copy()
    mask[:-1] |= mask[1:].copy()
    return mask


def _horizontal_rules(gray: np.ndarray, n_min: int) -> np.ndarray:
    rules = np.zeros(gray.shape, np.bool_)
    for i in range(0, gray.shape[0], STRIP):
        lo, hi = max(0, i - 1), min(gray.shape[0], i + STRIP + 1)
        mask = _thickened(_long_run_mask(gray[lo:hi] < DARK_INK_LEVEL, n_min))
        rules[i : i + STRIP] = mask[i - lo : i - lo + min(STRIP, gray.shape[0] - i)]
    return rules


def _vertical_rules(gray: np.ndarray, n_min: int) -> np.ndarray:
    rules = np.zeros(gray.shape, np.bool_)
    for j in range(0, gray.shape[1], STRIP):
        lo, hi = max(0, j - 1), min(gray.shape[1], j + STRIP + 1)
        mask = _thickened(_long_run_mask(np.ascontiguousarray(gray[:, lo:hi].T) < DARK_INK_LEVEL, n_min))
        rules[:, j : j + STRIP] = mask[j - lo : j - lo + min(STRIP, gray.shape[1] - j)].T
    return rules


def erase_long_lines(gray: np.ndarray, n_min: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    horizontal, vertical = _horizontal_rules(gray, n_min), _vertical_rules(gray, n_min)
    out = gray.copy()
    out[horizontal | vertical] = 255
    return out, horizontal, vertical


def rule_between(rules: np.ndarray | None, xa: float, xb: float, ya: float, yb: float) -> bool:
    if rules is None:
        return False
    x0, x1 = max(int(xa), 0), int(xb)
    y0, y1 = max(int(ya), 0), int(yb)
    return x1 > x0 and y1 > y0 and bool(rules[y0:y1, x0:x1].any())


def tiles(img: np.ndarray, zoom: float) -> list[tuple[int, int, int, int]]:
    h, w = img.shape
    core, overlap = max(256, int(TILE_CORE_PT * zoom)), int(TILE_OVERLAP_PT * zoom)
    out = []
    for y in range(0, h, core):
        for x in range(0, w, core):
            y0, x0, y1, x1 = (
                max(0, y - overlap),
                max(0, x - overlap),
                min(h, y + core + overlap),
                min(w, x + core + overlap),
            )
            if np.count_nonzero(img[y0:y1, x0:x1] < DARK_INK_LEVEL) >= MIN_TILE_INK:
                out.append((y0, x0, y1, x1))
    return out
