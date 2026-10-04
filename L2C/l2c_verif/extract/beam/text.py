from __future__ import annotations

import re
from statistics import median

from ...models import Armature
from ...rebar import BAR_SIZES, norm_text, spacing_to_mm

RE_ID = r"P\s?-?\s?[0-9IOL](?:\s?[0-9IOL]){1,3}[A-Z]?|PC-?\d{1,3}"
RE_TITLE = re.compile(rf"^(?P<id>{RE_ID})(?![0-9A-Z])\s*(?:[-:]\s*|$|(?=\d))(?P<rest>.*)$")
RE_DIMS = re.compile(r"\d\s*(?:\"|MM)?\s*X\s*\d|\d\s*@\s*\d|^\s*-?\s*$|^\s*\d")
RE_PLAN_BAR = re.compile(r"(?<![\d.])(?P<qty>\d{1,2})\s*-\s*(?P<size>\d{2}M)\b")
RE_DA_BAR = re.compile(
    r"(?<![\w.@/'\"-])(?P<qty>\d{1,3})(?:\s*X\s*(?P<qty2>\d{1,2}))?\s+(?P<size>\d{2}M)(?![A-Z0-9])"
)
RE_SIZE_AT = re.compile(
    r"(?<![\d-])(?P<size>\d{2}M)\s*@\s*(?P<sp>\d+\s*'\s*-?\s*\d+\s*\"|\d+(?:\.\d+)?\s*(?:\"|MM)?)"
)
RE_ETRIERS = re.compile(r"(?P<qty>\d{1,2})\s*ETRIERS?\s*(?P<size>\d{2}M)")
RE_AT = re.compile(r"@\s*(\d+\s*'\s*-?\s*\d+\s*\"|\d+(?:\.\d+)?\s*(?:\"|MM)?)")
RE_MARK = re.compile(r"^\s*(\d{2}[A-Z]{1,3}[0-9][0-9A-Z\-X]*)")
RE_TOP = re.compile(r"\b(?:HAUT|H(?![A-EG-Z]))")
RE_BOTTOM = re.compile(r"\b(?:BAS|B(?![A-EG-Z]))")
RE_U_BAR = re.compile(r"U\s*BAR")
RE_STIRRUP = re.compile(r"\bETR|\b\d{2}T+\d")
RE_OCR_TEN = re.compile(r"(?<![A-Z0-9])[IL1][O0](?=[MTUZ](?:\b|\d|[A-Z]))")
RE_BROKEN_TITLE = re.compile(r"^P\S{1,5}\s*-\s*\d")
RE_BAR_LIKE = re.compile(r"\d{3,5}\s*[HB]\b|@\s*\d|\bETR\b|\bBAR\b")
RE_TITLE_LIKE = re.compile(r"^\W*P\s?\S{2,4}\s")
RE_LENGTH_SIDE = re.compile(r"\d\s*[HB]\b")
RE_PLAIN_ID = re.compile(r"^P-?([0-9IOL]{2,4})([A-Z]?)$")
TITLE_SIZE_RATIO = 1.3


def fix_ocr(text: str) -> str:
    return RE_OCR_TEN.sub("10", text)


def suspicious(text: str) -> bool:
    t = fix_ocr(norm_text(text))
    if RE_BROKEN_TITLE.match(t) and not RE_TITLE.match(t):
        return True
    return bool(RE_BAR_LIKE.search(t)) and not any(
        m.group("size") in BAR_SIZES for m in RE_DA_BAR.finditer(t)
    )


def worth_rereading(text: str) -> bool:
    t = fix_ocr(norm_text(text))
    return suspicious(text) or bool(RE_TITLE_LIKE.match(t)) or bool(RE_LENGTH_SIDE.search(t))


def norm_id(raw: str) -> str:
    t = re.sub(r"\s+", "", raw.upper())
    match = RE_PLAIN_ID.match(t)
    if match:
        digits = match.group(1).translate(str.maketrans("IOL", "101"))
        return f"P{digits}{match.group(2)}"
    return t


def _label_size(lines: list[dict]) -> float:
    sizes = [
        ln["size"]
        for ln in lines
        if RE_PLAN_BAR.search(norm_text(ln["text"])) or RE_DA_BAR.search(norm_text(ln["text"]))
    ]
    return median(sizes) if sizes else 0.0


def _continuation(lines: list[dict], title: dict) -> dict | None:
    box, size = title["bbox"], max(title["size"], 1)
    following = [
        o
        for o in lines
        if o is not title
        and abs(o["bbox"][1] - box[1]) < 0.4 * size
        and 0 <= o["bbox"][0] - box[2] < 3 * size
    ]
    return min(following, key=lambda o: o["bbox"][0]) if following else None


def _title(lines: list[dict], ln: dict, reference_size: float) -> tuple | None:
    match = RE_TITLE.match(norm_text(ln["text"])) if ln["dir"] == (1, 0) else None
    if not match:
        return None
    rest, box, text = match.group("rest"), ln["bbox"], ln["text"].strip()
    following = _continuation(lines, ln) if not rest.strip() or rest.strip() == "-" else None
    if following is not None:
        rest = norm_text(following["text"])
        box = (
            box[0],
            min(box[1], following["bbox"][1]),
            following["bbox"][2],
            max(box[3], following["bbox"][3]),
        )
        text = f"{text} {following['text'].strip()}"
    if not RE_DIMS.search(rest.lstrip(" -")):
        return None
    if reference_size and ln["size"] < TITLE_SIZE_RATIO * reference_size and not ln.get("ocr"):
        return None
    return (norm_id(match.group("id")), text, box, ln["size"])


def titles(lines: list[dict]) -> list[tuple[str, str, tuple, float]]:
    reference_size = _label_size(lines)
    return [t for t in (_title(lines, ln, reference_size) for ln in lines) if t is not None]


def make_bar(role: str, size: str, quantity=None, spacing=None, mark=None) -> Armature:
    return Armature(role=role, repere=mark or role, diametre=size, quantite=quantity, espacement_mm=spacing)


def _added_stirrups(text: str) -> list[tuple] | None:
    match = RE_ETRIERS.search(text)
    if match and match.group("size") in BAR_SIZES:
        return [("LIG ADD", make_bar("LIG ADD", match.group("size"), int(match.group("qty"))), True)]
    return None


def _plan_bars(text: str) -> list[tuple]:
    out = []
    for match in RE_PLAN_BAR.finditer(text):
        size, quantity = match.group("size"), int(match.group("qty"))
        if size not in BAR_SIZES:
            continue
        if "ADD" in text:
            zone = "LIG ADD" if size == "10M" else "ADD"
            out.append((zone, make_bar(zone, size, quantity), True))
        else:
            out.append(("LONG", make_bar("LONG", size, quantity), False))
    return out


def _shop_zone(rest: str, has_spacing: bool) -> tuple[str, bool]:
    if RE_U_BAR.search(rest):
        return "LIG U", True
    if RE_STIRRUP.search(rest):
        return ("LIG ADD" if "ADD" in rest else "LIG"), True
    if has_spacing:
        return "PEAU", True
    if "ADD" in rest:
        return "ADD", True
    zone = "SUP" if RE_TOP.search(rest) else "INF" if RE_BOTTOM.search(rest) else "LONG"
    return zone, zone != "LONG"


def _shop_bars(text: str) -> list[tuple]:
    matches = [m for m in RE_DA_BAR.finditer(text) if m.group("size") in BAR_SIZES]
    out = []
    for i, match in enumerate(matches):
        rest = text[match.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        quantity = int(match.group("qty")) * (int(match.group("qty2")) if match.group("qty2") else 1)
        mark, spacing = RE_MARK.match(rest), RE_AT.search(rest)
        zone, explicit = _shop_zone(rest, spacing is not None)
        bar = make_bar(
            zone,
            match.group("size"),
            quantity,
            spacing_to_mm(spacing.group(1)) if spacing else None,
            mark.group(1) if mark else None,
        )
        out.append((zone, bar, explicit))
    return out


def _spaced_bars(text: str, skin_context: bool) -> list[tuple]:
    zone = "PEAU" if (skin_context or "PEAU" in text) else "LIG"
    return [
        (zone, make_bar(zone, m.group("size"), None, spacing_to_mm(m.group("sp"))), True)
        for m in RE_SIZE_AT.finditer(text)
        if m.group("size") in BAR_SIZES
    ]


def parse_line(text: str, skin_context: bool) -> list[tuple[str, Armature, bool]]:
    stirrups = _added_stirrups(text)
    if stirrups:
        return stirrups
    shop = _shop_bars(text)
    return _plan_bars(text) + shop + ([] if shop else _spaced_bars(text, skin_context))
