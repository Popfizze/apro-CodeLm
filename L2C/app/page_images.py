from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz

from data_io import OUTPUTS, PdfIndex, doc_sources, file_key, log, read_json, safe_stem, sorties

REPORT_PAGE_PX = 1800
ANNOTATED_PAGE_PX = 2200
PLAN_PAGE_PX = 2000
PLAN_THUMB_PX = 360
ATELIER_PAGE_PX = 1800
RUN_PAGES = (
    ("pages_rapport", "report_pdf", "rapport", REPORT_PAGE_PX),
    ("pages_annote", "annotated_pdf", "annote", ANNOTATED_PAGE_PX),
)
DOC_IMAGES = {
    "plan": ("_plans", "plan", PLAN_PAGE_PX, "png"),
    "atelier": ("_ateliers", "page", ATELIER_PAGE_PX, "jpg"),
}


def page_sizes(pdf: Path) -> list[list[float]]:
    with fitz.open(pdf) as doc:
        return [[round(page.rect.width, 2), round(page.rect.height, 2)] for page in doc]


def _write_index(index_path: Path, key: str, files: list[str], sizes: list) -> None:
    index_path.write_text(json.dumps({"key": key, "files": files, "sizes": sizes}), encoding="utf-8")


def _cached_pages(pdf: Path, out_dir: Path, key: str, index_path: Path, with_sizes: bool) -> tuple | None:
    cached = read_json(index_path, {})
    files = cached.get("files") if isinstance(cached, dict) else None
    if cached.get("key") != key or not files or not all((out_dir / name).is_file() for name in files):
        return None
    sizes = cached.get("sizes")
    if with_sizes and not (isinstance(sizes, list) and len(sizes) == len(files)):
        sizes = page_sizes(pdf)
        _write_index(index_path, key, files, sizes)
    return files, sizes


def _image_bytes(pix: fitz.Pixmap, fmt: str) -> bytes:
    return pix.tobytes("png") if fmt == "png" else pix.tobytes("jpg", jpg_quality=80)


def _render_all(pdf: Path, out_dir: Path, prefix: str, max_px: int, fmt: str) -> tuple[list[str], list]:
    files, sizes = [], []
    out_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf) as doc:
        for number, page in enumerate(doc, 1):
            zoom = max_px / max(page.rect.width, page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            name = f"{prefix}_{number}.{fmt}"
            (out_dir / name).write_bytes(_image_bytes(pix, fmt))
            files.append(name)
            sizes.append([round(page.rect.width, 2), round(page.rect.height, 2)])
    return files, sizes


def render_pages(
    pdf: Path,
    out_dir: Path,
    image: tuple[str, int, str],
    rel_base: str,
    force: bool,
    with_sizes: bool = False,
) -> tuple[list[str], list | None]:
    prefix, max_px, fmt = image
    key = file_key(pdf, max_px, fmt)
    index_path = out_dir / f"_{prefix}.json"
    found = None if force else _cached_pages(pdf, out_dir, key, index_path, with_sizes)
    if found is None:
        found = _render_all(pdf, out_dir, prefix, max_px, fmt)
        _write_index(index_path, key, *found)
    files, sizes = found
    return [f"{rel_base}/{name}" for name in files], sizes


def build_run_pages(res_dir: Path, run: dict, out_dir: Path, force: bool) -> dict:
    pages = {"pages_rapport": [], "pages_annote": []}
    dossier = safe_stem(run["dossier"])
    for key, sortie, prefix, max_px in RUN_PAGES:
        src = res_dir / (sorties(run).get(sortie) or OUTPUTS[sortie])
        if not src.is_file():
            continue
        try:
            target = out_dir / "reports" / dossier / "pages"
            pages[key] = render_pages(
                src, target, (prefix, max_px, "png"), f"reports/{dossier}/pages", force
            )[0]
        except Exception as exc:
            log(f"  ! page rendering failed for {src.name}: {exc}")
    return pages


def _doc_pages(path: Path, base: Path, kind: str, force: bool) -> dict:
    folder_name, prefix, max_px, fmt = DOC_IMAGES[kind]
    rel = f"reports/{folder_name}/{base.name}"
    views, sizes = render_pages(path, base, (prefix, max_px, fmt), rel, force, with_sizes=True)
    thumbs = render_pages(path, base, ("vignette", PLAN_THUMB_PX, "jpg"), rel, force)[0]
    return {"pages": len(views), "vues": views, "vignettes": thumbs, "tailles": sizes}


def build_doc_pages(run: dict, index: PdfIndex, out_dir: Path, force: bool, kind: str) -> list[dict]:
    docs = []
    for fichier, path in doc_sources(run, index, kind):
        folder = hashlib.sha1(file_key(path).encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
        base = out_dir / "reports" / DOC_IMAGES[kind][0] / folder
        try:
            pages = _doc_pages(path, base, kind, force)
        except Exception as exc:
            log(f"  ! page rendering failed for {fichier}: {exc}")
            continue
        docs.append({"fichier": Path(fichier).name, **pages})
    return docs
