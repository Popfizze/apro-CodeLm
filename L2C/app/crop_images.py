from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import fitz

from data_io import PdfIndex, item_bbox, item_page, log, read_json, safe_stem

CROP_STATUSES = {"non_conforme", "manquant_atelier", "ajoute_atelier"}
PAD_PT = 120.0
ZOOM = 2.5
MAX_CROP_PX = 2000
ITEM_PAD_PT = 110.0
ITEM_ZOOM = 1.8
MAX_ITEM_CROP_PX = 1400
HIGHLIGHT = (0.86, 0.1, 0.1)
MAX_LOGGED_FAILURES = 5


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def _page(index: PdfIndex, pdf: Path, page_no: int, message: str) -> fitz.Page:
    doc = index.open(pdf)
    if not 1 <= page_no <= doc.page_count:
        raise ValueError(message.format(page=page_no, count=doc.page_count))
    return doc[page_no - 1]


def _padded(page: fitz.Page, bbox, pad: float) -> fitz.Rect:
    rect = fitz.Rect(bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad) & page.rect
    if rect.is_empty:
        raise ValueError("bbox outside the page")
    return rect


def _highlight(page: fitz.Page, target: fitz.Rect):
    try:
        annot = page.add_rect_annot(target + (-3, -3, 3, 3))
        annot.set_colors(stroke=HIGHLIGHT)
        annot.set_border(width=3)
        annot.update()
    except Exception:
        return None
    return annot


def render_crop(index: PdfIndex, pdf: Path, page_no: int, bbox: list[float], out: Path) -> None:
    page = _page(index, pdf, page_no, "page {page} out of range (1..{count})")
    target = fitz.Rect(bbox)
    clip = _padded(page, target, PAD_PT)
    zoom = min(ZOOM, MAX_CROP_PX / max(clip.width, clip.height))
    annot = _highlight(page, target)
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
        out.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(out))
    finally:
        if annot is not None:
            page.delete_annot(annot)


class CropBuilder:
    def __init__(self, crops_dir: Path, rel_prefix: str, force: bool):
        self.dir = crops_dir
        self.rel_prefix = rel_prefix
        self.force = force
        self.manifest_path = crops_dir / "_manifest.json"
        self.manifest: dict = read_json(self.manifest_path, {}) if not force else {}
        self.stats = {"rendered": 0, "cached": 0, "copied": 0, "failed": 0}
        self.used_names: dict[str, str] = {}

    def name_for(self, finding_id: str) -> str:
        stem = safe_stem(finding_id)
        owner = self.used_names.get(stem)
        if owner is not None and owner != finding_id:
            stem = f"{stem}_{_sha1(finding_id)[:8]}"
        self.used_names[stem] = finding_id
        return stem

    def _render(self, index: PdfIndex, item: dict, out_name: str) -> bool:
        pdf, bbox, page_no = index.find(item.get("fichier")), item_bbox(item), item_page(item)
        if pdf is None or bbox is None or page_no is None:
            return False
        key = f"{pdf}|{pdf.stat().st_mtime_ns}|{page_no}|{bbox}|{PAD_PT}|{ZOOM}"
        if not self.force and (self.dir / out_name).is_file() and self.manifest.get(out_name) == key:
            self.stats["cached"] += 1
            return True
        try:
            render_crop(index, pdf, page_no, bbox, self.dir / out_name)
        except Exception as exc:
            log(f"  ! crop failed for {out_name}: {exc}")
            return False
        self.manifest[out_name] = key
        self.stats["rendered"] += 1
        return True

    def _copy_fallback(self, fallback: Path | None, out_name: str) -> bool:
        if fallback is None or not fallback.is_file():
            return False
        self.dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fallback, self.dir / out_name)
        self.manifest.pop(out_name, None)
        self.stats["copied"] += 1
        return True

    def build(self, index: PdfIndex, item: dict | None, out_name: str, fallback: Path | None) -> str | None:
        if not item:
            return None
        if self._render(index, item, out_name) or self._copy_fallback(fallback, out_name):
            return f"{self.rel_prefix}/{out_name}"
        self.stats["failed"] += 1
        return None

    def save(self) -> None:
        if self.manifest:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.manifest_path.write_text(json.dumps(self.manifest, indent=0), encoding="utf-8")


def _needs_crop(statut, conforme_done: int, max_conforme: int) -> bool:
    if statut == "conforme":
        return conforme_done < max_conforme
    return statut in CROP_STATUSES


def _finding_crops(finding: dict, by_id: dict, res_dir: Path, index: PdfIndex, crops: CropBuilder) -> None:
    fid = str(finding.get("id") or "")
    if not fid:
        return
    stem = crops.name_for(fid)
    for side in ("plan", "atelier"):
        item = by_id.get(str(finding.get(f"{side}_item")))
        rel = crops.build(index, item, f"{stem}_{side}.png", res_dir / "crops" / f"{fid}_{side}.png")
        if rel:
            finding[f"crop_{side}"] = rel


def build_finding_crops(
    findings: list[dict],
    items: list[dict],
    res_dir: Path,
    index: PdfIndex,
    crops: CropBuilder,
    max_conforme: int,
) -> None:
    by_id = {str(i.get("id")): i for i in items if i.get("id") is not None}
    conforme_done = 0
    for finding in findings:
        finding.pop("crop_plan", None)
        finding.pop("crop_atelier", None)
        statut = finding.get("statut")
        if not _needs_crop(statut, conforme_done, max_conforme):
            continue
        if statut == "conforme":
            conforme_done += 1
        _finding_crops(finding, by_id, res_dir, index, crops)
    crops.save()
    log(f"  crops: {crops.stats}")


class ItemCropBuilder:
    def __init__(self, crops_dir: Path, force: bool):
        self.dir = crops_dir
        self.force = force
        self.index_path = crops_dir / "_index.json"
        self.clips: dict = read_json(self.index_path, {}) if not force else {}
        self.stats = {"rendered": 0, "cached": 0, "failed": 0}

    def _render(self, index: PdfIndex, pdf: Path, page_no: int, bbox, out: Path) -> list[float]:
        page = _page(index, pdf, page_no, "page {page} out of range")
        rect = _padded(page, bbox, ITEM_PAD_PT)
        zoom = min(ITEM_ZOOM, MAX_ITEM_CROP_PX / max(rect.width, rect.height))
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)
        self.dir.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pix.tobytes("jpg", jpg_quality=78))
        return [round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)]

    def _clip(self, index: PdfIndex, item: dict, source: tuple, name: str):
        clip = self.clips.get(name)
        if clip is not None and (self.dir / name).is_file() and not self.force:
            self.stats["cached"] += 1
            return clip
        try:
            clip = self._render(index, *source, self.dir / name)
        except Exception as exc:
            self.stats["failed"] += 1
            if self.stats["failed"] <= MAX_LOGGED_FAILURES:
                log(f"  ! item crop failed for {item.get('id')}: {exc}")
            return None
        self.clips[name] = clip
        self.stats["rendered"] += 1
        return clip

    def build(self, index: PdfIndex, item: dict) -> None:
        item.pop("crop", None)
        item.pop("crop_clip", None)
        pdf, bbox, page_no = index.find(item.get("fichier")), item_bbox(item), item_page(item)
        if page_no is None or pdf is None or bbox is None:
            return
        key = f"{pdf}|{pdf.stat().st_mtime_ns}|{page_no}|{bbox}|{ITEM_PAD_PT}|{ITEM_ZOOM}"
        name = _sha1(key)[:20] + ".jpg"
        clip = self._clip(index, item, (pdf, page_no, bbox), name)
        if clip is not None:
            item["crop"] = f"crops/items/{name}"
            item["crop_clip"] = clip

    def save(self) -> None:
        if self.clips:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.index_path.write_text(json.dumps(self.clips, separators=(",", ":")), encoding="utf-8")
