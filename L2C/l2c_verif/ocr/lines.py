from __future__ import annotations

import re
from statistics import median

from .image import rule_between
from .text import clean_word, fix_role_label, fix_text

MIN_WORD_CONF = 20.0
CAP_HEIGHT_PER_FONT_SIZE = 0.72
FONT_ASCENT, FONT_DESCENT = 0.9, 0.2
SPLIT_GAP_IN_CAPS = 2.0
MERGE_GAP_IN_CAPS = 1.6
RULE_SPLIT_MIN_GAP_IN_CAPS = 0.8
LABEL_VALUE_GAP_IN_CAPS = 5.0
KEEP_SYMBOLS = {"@", "-", "(", ")", '"', "'", ":", "/", "&", "#", "=", "+"}
RE_CAPS_OR_DIGITS = re.compile(r"[A-Z0-9.:/,\-]+")
RE_ALNUM = re.compile(r"[A-Za-z0-9]")
RE_LABEL_HEAD = re.compile(r"[A-Za-z.]{2,6}:?")
RE_SHORT_LOWER = re.compile(r"[a-z]{1,3}")
DEDUPE_CELL = 64.0


def _caps_or_digits(text: str) -> bool:
    return bool(RE_CAPS_OR_DIGITS.fullmatch(text))


def _score(words: list[dict]) -> float:
    return sum(w["conf"] / 100.0 * sum(ch.isalnum() for ch in w["text"]) for w in words)


def _continues_on_same_baseline(head: dict, ln: dict, rules=None) -> bool:
    cap = head["cap"]
    if abs(head["base"] - ln["base"]) > 0.35 * cap or max(cap, ln["cap"]) > 1.4 * min(cap, ln["cap"]):
        return False
    gap = ln["x0"] - head["x1"]
    top, bottom = ln["base"] - 0.8 * cap, ln["base"] - 0.2 * cap
    if gap > RULE_SPLIT_MIN_GAP_IN_CAPS * cap and rule_between(rules, head["x1"], ln["x0"], top, bottom):
        return False
    if -0.3 * cap <= gap <= MERGE_GAP_IN_CAPS * cap:
        return True
    head_is_label = RE_LABEL_HEAD.fullmatch(" ".join(w["text"] for w in head["words"]))
    return (
        bool(head_is_label)
        and 0 <= gap <= LABEL_VALUE_GAP_IN_CAPS * cap
        and bool(re.match(r"\d", ln["words"][0]["text"]))
    )


def _kept_word(word: dict) -> dict | None:
    text = clean_word(word["text"])
    if word["conf"] < MIN_WORD_CONF or not text or (not RE_ALNUM.search(text) and text not in KEEP_SYMBOLS):
        return None
    return {**word, "text": text}


def _grouped_words(words: list[dict]) -> list[list[dict]]:
    groups: dict[tuple, list[dict]] = {}
    for word in words:
        kept = _kept_word(word)
        if kept is not None:
            groups.setdefault(kept["key"], []).append(kept)
    return list(groups.values())


def _without_tall_marks(words: list[dict], cap: float) -> list[dict]:
    return [
        w
        for w in words
        if not (w["h"] > 1.7 * cap and len(w["text"]) <= 2 and not re.search(r"\d", w["text"]))
        and not (w["h"] > 1.8 * cap and len(w["text"]) == 1)
    ]


def _separated(previous: dict, word: dict, cap: float, rules) -> bool:
    gap = word["l"] - (previous["l"] + previous["w"])
    top, bottom = max(previous["t"], word["t"]), min(previous["t"] + previous["h"], word["t"] + word["h"])
    if gap > RULE_SPLIT_MIN_GAP_IN_CAPS * cap and rule_between(
        rules, previous["l"] + previous["w"], word["l"], top, bottom
    ):
        return True
    limit = LABEL_VALUE_GAP_IN_CAPS if previous["text"].endswith(":") else SPLIT_GAP_IN_CAPS
    return gap > limit * cap


def _split_segments(words: list[dict], cap: float, rules) -> list[list[dict]]:
    words.sort(key=lambda w: w["l"])
    segments, current = [], [words[0]]
    for word in words[1:]:
        if _separated(current[-1], word, cap, rules):
            segments.append(current)
            current = [word]
        else:
            current.append(word)
    segments.append(current)
    return segments


def _segments(words: list[dict], rules) -> list[list[dict]]:
    segments = []
    for group in _grouped_words(words):
        cap = median([w["h"] for w in group if _caps_or_digits(w["text"])] or [w["h"] for w in group])
        kept = _without_tall_marks(group, cap)
        if kept:
            segments += _split_segments(kept, cap, rules)
    return segments


def _segment_line(segment: list[dict]) -> dict:
    reference = [w for w in segment if _caps_or_digits(w["text"])] or segment
    return {
        "words": segment,
        "tile": segment[0]["key"][0],
        "x0": segment[0]["l"],
        "x1": max(w["l"] + w["w"] for w in segment),
        "cap": median(w["h"] for w in reference),
        "base": median(w["t"] + w["h"] for w in reference),
    }


def _merge_baselines(lines: list[dict], rules) -> list[dict]:
    lines.sort(key=lambda ln: (ln["tile"], ln["x0"]))
    merged: list[dict] = []
    for ln in lines:
        head = next(
            (
                a
                for a in reversed(merged)
                if a["tile"] == ln["tile"] and _continues_on_same_baseline(a, ln, rules)
            ),
            None,
        )
        if head is None:
            merged.append(ln)
        else:
            head["words"] += ln["words"]
            head["x1"] = max(head["x1"], ln["x1"])
    return merged


def _confidence(words: list[dict]) -> float:
    weights = [max(1, len(w["text"])) for w in words]
    return sum(w["conf"] * k for w, k in zip(words, weights, strict=True)) / sum(weights)


def _reliable(words: list[dict], confidence: float) -> bool:
    alnum = sum(ch.isalnum() for w in words for ch in w["text"])
    return not (alnum == 0 or (alnum <= 2 and confidence < 50) or confidence < 30)


def _finished_line(ln: dict) -> dict | None:
    words = ln["words"]
    confidence = _confidence(words)
    if not _reliable(words, confidence):
        return None
    text = fix_role_label(fix_text(" ".join(w["text"] for w in words)))
    if not text or RE_SHORT_LOWER.fullmatch(text):
        return None
    return {
        "text": text,
        "x0": ln["x0"],
        "x1": ln["x1"],
        "cap": ln["cap"],
        "base": ln["base"],
        "conf": round(confidence, 1),
        "score": _score(words),
    }


def pass_lines(words: list[dict], rules=None) -> list[dict]:
    lines = [_segment_line(segment) for segment in _segments(words, rules)]
    finished = (_finished_line(ln) for ln in _merge_baselines(lines, rules))
    return [ln for ln in finished if ln is not None]


def to_visual(ln: dict, zoom: float, rotated: bool, img_h: int, origin: tuple[float, float]) -> dict:
    size = ln["cap"] / CAP_HEIGHT_PER_FONT_SIZE
    fy0, fy1, iy0 = ln["base"] - FONT_ASCENT * size, ln["base"] + FONT_DESCENT * size, ln["base"] - ln["cap"]
    if rotated:
        box = (fy0, img_h - ln["x1"], fy1, img_h - ln["x0"])
        ink = (iy0, img_h - ln["x1"], ln["base"], img_h - ln["x0"])
        start, direction = (ln["base"], img_h - ln["x0"]), (0, -1)
    else:
        box = (ln["x0"], fy0, ln["x1"], fy1)
        ink = (ln["x0"], iy0, ln["x1"], ln["base"])
        start, direction = (ln["x0"], ln["base"]), (1, 0)
    ox, oy = origin

    def to_page(b):
        return (b[0] / zoom + ox, b[1] / zoom + oy, b[2] / zoom + ox, b[3] / zoom + oy)

    return {
        "text": ln["text"],
        "bbox": to_page(box),
        "ink": to_page(ink),
        "size": size / zoom,
        "dir": direction,
        "conf": ln["conf"],
        "score": ln["score"],
        "origin": (start[0] / zoom + ox, start[1] / zoom + oy),
    }


def _area(box) -> float:
    return max((box[2] - box[0]) * (box[3] - box[1]), 1e-6)


def _clashes(ink, kept: list[dict], nearby: set[int]) -> bool:
    x0, y0, x1, y1 = ink
    for k in nearby:
        a0, b0, a1, b1 = kept[k]["ink"]
        iw, ih = min(x1, a1) - max(x0, a0), min(y1, b1) - max(y0, b0)
        if iw > 0 and ih > 0 and iw * ih > 0.3 * min(_area(ink), _area(kept[k]["ink"])):
            return True
    return False


def dedupe(lines: list[dict]) -> list[dict]:
    grid: dict[tuple[int, int], list[int]] = {}
    kept: list[dict] = []
    for ln in sorted(lines, key=lambda line: -line["score"]):
        x0, y0, x1, y1 = ln["ink"]
        cells = [
            (i, j)
            for i in range(int(x0 // DEDUPE_CELL), int(x1 // DEDUPE_CELL) + 1)
            for j in range(int(y0 // DEDUPE_CELL), int(y1 // DEDUPE_CELL) + 1)
        ]
        if _clashes(ln["ink"], kept, {k for c in cells for k in grid.get(c, ())}):
            continue
        for c in cells:
            grid.setdefault(c, []).append(len(kept))
        kept.append(ln)
    return kept
