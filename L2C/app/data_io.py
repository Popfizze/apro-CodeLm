from __future__ import annotations

import contextlib
import json
import re
import shutil
import unicodedata
from pathlib import Path

import fitz

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
DEFAULT_HALF_BOX = (40.0, 15.0)
OUTPUTS = {
    "items_plan": "items_plan.json",
    "items_atelier": "items_atelier.json",
    "findings": "findings.json",
    "summary": "summary.json",
    "annexe_a_plan": "annexe_a_plan.json",
    "annexe_a_atelier": "annexe_a_atelier.json",
    "report_pdf": "report.pdf",
    "annotated_pdf": "annotated.pdf",
}
DELIVERABLES = ["report_pdf", "annotated_pdf", "annexe_a_plan", "annexe_a_atelier"]


def log(message: str) -> None:
    print(message, flush=True)


def read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log(f"  ! unreadable JSON {path.name}: {exc}")
        return default


def dict_list(value) -> list[dict]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def norm_name(name: str) -> str:
    return unicodedata.normalize("NFC", Path(str(name).replace("\\", "/")).name).casefold()


def safe_stem(text: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("._")
    return stem[:140] or "finding"


def file_key(path: Path, *extra) -> str:
    st = path.stat()
    return "|".join([str(path.resolve()), str(st.st_size), str(st.st_mtime_ns), *map(str, extra)])


def sorties(run: dict) -> dict:
    return run.get("sorties") if isinstance(run.get("sorties"), dict) else {}


class PdfIndex:
    def __init__(self, roots: list[Path]):
        self.paths: dict[str, Path] = {}
        for root in roots:
            if root.is_dir():
                for pdf in root.rglob("*.pdf"):
                    self.paths.setdefault(norm_name(pdf.name), pdf)
        self._docs: dict[Path, fitz.Document] = {}

    def find(self, fichier: str | None) -> Path | None:
        return self.paths.get(norm_name(fichier)) if fichier else None

    def open(self, path: Path) -> fitz.Document:
        if path not in self._docs:
            self._docs[path] = fitz.open(path)
        return self._docs[path]

    def close(self) -> None:
        for doc in self._docs.values():
            with contextlib.suppress(Exception):
                doc.close()
        self._docs.clear()


def _bbox_corners(bbox) -> list[float] | None:
    if not isinstance(bbox, list | tuple) or len(bbox) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def item_bbox(item: dict) -> list[float] | None:
    corners = _bbox_corners(item.get("bbox"))
    if corners is not None:
        return corners
    try:
        x, y = float(item["x"]), float(item["y"])
    except (KeyError, TypeError, ValueError):
        return None
    hw, hh = DEFAULT_HALF_BOX
    return [x - hw, y - hh, x + hw, y + hh]


def item_page(item: dict) -> int | None:
    try:
        return int(item.get("page"))
    except (TypeError, ValueError):
        return None


def _up_to_date(src: Path, dst: Path) -> bool:
    st = src.stat()
    return dst.is_file() and dst.stat().st_size == st.st_size and dst.stat().st_mtime_ns == st.st_mtime_ns


def _copy(src: Path, reports_dir: Path) -> Path | None:
    dst = reports_dir / src.name
    try:
        if not _up_to_date(src, dst):
            reports_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    except OSError as exc:
        log(f"  ! could not copy {src.name}: {exc}")
        return None
    return dst


def copy_deliverables(res_dir: Path, run: dict, reports_dir: Path) -> dict:
    out = dict.fromkeys(DELIVERABLES)
    for key in DELIVERABLES:
        src = Path(str(sorties(run).get(key) or OUTPUTS[key]))
        src = src if src.is_absolute() else res_dir / src
        dst = _copy(src, reports_dir) if src.is_file() else None
        if dst is not None:
            out[key] = f"reports/{reports_dir.name}/{dst.name}"
    return out


def source_roots(data_root: Path, projet: str, dossier: str, run: dict) -> list[Path]:
    roots = [
        data_root / projet,
        APP_DIR / "uploads" / projet,
        APP_DIR / "uploads" / dossier,
        data_root / dossier,
    ]
    for entry in run["entrees"]["plan"] + run["entrees"]["atelier"]:
        if entry.get("chemin"):
            roots.append((ROOT / str(entry["chemin"])).parent)
    seen, out = set(), []
    for root in roots:
        if str(root).casefold() not in seen:
            seen.add(str(root).casefold())
            out.append(root)
    return out


def _entry_path(entry: dict, index: PdfIndex) -> Path | None:
    if entry.get("chemin"):
        candidate = ROOT / str(entry["chemin"])
        if candidate.is_file():
            return candidate
    return index.find(entry.get("fichier"))


def doc_sources(run: dict, index: PdfIndex, kind: str) -> list[tuple[str, Path]]:
    found = []
    for entry in run["entrees"][kind]:
        path = _entry_path(entry, index)
        if path is not None:
            found.append((str(entry.get("fichier") or path.name), path))
    return found
