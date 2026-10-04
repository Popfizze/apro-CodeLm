from __future__ import annotations

import re

from ..models import Armature
from ..rebar import ROLE_ALIASES, bar_size, length_to_mm, norm_text, spacing_to_mm
from .schema import LlmBar, LlmBlock

RE_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _number_in(text: str, number: str) -> bool:
    return re.search(rf"(?<![\d.]){re.escape(number)}(?![\d])", text) is not None


def _count_in(text: str, number: str) -> bool:
    return re.search(rf"(?<![\d.@]){re.escape(number)}(?![\d.]|\s*M(?![A-Z])|\s*[\"'])", text) is not None


def _size_written(size: str, text: str, mark: str, mark_written: bool) -> bool:
    number = re.sub(r"\D", "", size)
    if not number:
        return False
    return bool(
        re.search(rf"(?<!\d){number}\s*M(?![A-Z])", text) or (mark_written and mark.startswith(number))
    )


def _spacing_written(spacing: str, text: str) -> bool:
    numbers = RE_NUMBER.findall(norm_text(spacing))
    return bool(numbers) and all(_number_in(text, n) for n in numbers)


def _line_failures(reading: LlmBar, line: str) -> list[str]:
    text = norm_text(line)
    mark = norm_text(reading.repere or "").replace(" ", "")
    mark_written = bool(mark) and mark in text.replace(" ", "")
    size = bar_size(reading.diametre or "")
    checks = [
        (bool(mark) and not mark_written, f"repere={reading.repere}"),
        (bool(size) and not _size_written(size, text, mark, mark_written), f"diametre={reading.diametre}"),
        (
            bool(reading.quantite) and not _count_in(text, str(reading.quantite)),
            f"quantite={reading.quantite}",
        ),
        (
            bool(reading.espacement) and not _spacing_written(reading.espacement, text),
            f"espacement={reading.espacement}",
        ),
    ]
    return [message for failed, message in checks if failed]


def ground_bar(reading: LlmBar, lines: list[str]) -> tuple[int | None, list[str]]:
    best: list[str] | None = None
    for i, line in enumerate(lines):
        failures = _line_failures(reading, line)
        if not failures:
            return i, []
        if best is None or len(failures) < len(best):
            best = failures
    return None, best if best is not None else _line_failures(reading, "")


def ungrounded_values(block: LlmBlock, raw_text: str) -> list[str]:
    lines = [ln for ln in raw_text.split("\n") if ln.strip()]
    return [failure for reading in block.barres for failure in ground_bar(reading, lines)[1]]


def _normalized_size(raw: str | None) -> str:
    size = bar_size(raw or "")
    if size and not size.endswith("M") and size.isdigit():
        return size + "M"
    return size


def _normalized_role(raw: str | None) -> str | None:
    key = norm_text(raw or "").replace(".", "").strip()
    return ROLE_ALIASES.get(key.split(" ")[0], key) if key else None


def to_armature(reading: LlmBar) -> Armature | None:
    size = _normalized_size(reading.diametre)
    if not size:
        return None
    role = _normalized_role(reading.role)
    return Armature(
        role=role,
        repere=(reading.repere or "").strip() or role,
        diametre=size,
        quantite=reading.quantite or None,
        espacement_mm=spacing_to_mm(reading.espacement),
        longueur_mm=length_to_mm(reading.longueur),
    )
