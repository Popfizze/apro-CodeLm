from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from .ocr import ocr_page_dict, page_has_text_layer
from .ocr import prefetch as prefetch_ocr
from .rebar import norm_text

PLAN_PATTERN = "L2C_PLAN_STR_*.pdf"
SHOP_DIR = "DA"

RE_SHEET = re.compile(r"^S-?\d{3}[A-Z]?$")
RE_LEVEL_NUMBER = re.compile(r"\bNIV(?:EAU)?\.?\s*-?\s*(\d+)")
RE_GROUND_FLOOR = re.compile(r"REZ.?DE.?CHAUSSEE|\bRDC\b")
RE_BASEMENT = re.compile(r"SOUS.?SOL|\bSS\d?\b")
RE_BASEMENT_NUMBER = re.compile(r"\bSS(\d)\b")
RE_FOUNDATION_TITLE = re.compile(r"FONDATION|SEMELLE|RADIER")
RE_DRAWING_TITLE = re.compile(r"PLAN|ELEVATION|COUPE|DETAIL")
FIXED_LEVELS = [
    (re.compile(r"\bTOIT\b"), "TOIT"),
    (re.compile(r"FONDATION|EMPATTEMENT|SEMELLE|\bFND\b|\bFDN\b"), "FONDATION"),
]

SERIES_TYPE = {
    "0": "fondation",
    "1": "fondation",
    "2": "fondation",
    "3": "poutre",
    "4": "mur",
    "5": "colonne",
    "6": "dalle",
}

DA_CATEGORY_TYPE = [
    (r"COLONNE", "colonne"),
    (r"DALLE", "dalle"),
    (r"POUTRE", "poutre"),
    (r"MUR|REFEND|CISAIL", "mur"),
    (r"FONDATION|SEMELLE|RADIER", "fondation"),
]


@dataclass
class PageRef:
    source: str
    path: Path
    fichier: str
    page: int
    width: float
    height: float
    feuillet: str | None = None
    series: str | None = None
    type_element: str | None = None
    titre: str | None = None
    niveau: str | None = None
    categorie: str | None = None
    lines: list[dict] = field(default_factory=list, repr=False)
    ocr: bool = False

    def __post_init__(self):
        self.ocr = self.ocr or any(ln.get("ocr") for ln in self.lines)

    @property
    def key(self) -> str:
        return f"{Path(self.fichier).stem}_p{self.page}"


def plan_pdfs(project_dir: Path) -> list[Path]:
    return sorted(Path(project_dir).glob(PLAN_PATTERN))


def shop_pdfs(project_dir: Path) -> list[Path]:
    return sorted((Path(project_dir) / SHOP_DIR).rglob("*.pdf"))


def _basement(text: str) -> str:
    number = RE_BASEMENT_NUMBER.search(text)
    return f"SOUS-SOL {number.group(1)}" if number else "SOUS-SOL"


def normalize_level(text: str | None) -> str | None:
    if not text:
        return None
    t = norm_text(text)
    if "APPENTIS" in t:
        return "TOIT APPENTIS"
    if "TREFOND" in t:
        return "TREFOND"
    number = RE_LEVEL_NUMBER.search(t)
    if number:
        return f"NIVEAU {int(number.group(1))}"
    if RE_GROUND_FLOOR.search(t):
        return "RDC"
    if RE_BASEMENT.search(t):
        return _basement(t)
    return next((level for pattern, level in FIXED_LEVELS if pattern.search(t)), None)


def _visual_line(line: dict, page: fitz.Page) -> tuple[tuple, tuple]:
    bbox, direction = line["bbox"], line["dir"]
    if page.rotation:
        matrix = page.rotation_matrix
        bbox = tuple(fitz.Rect(bbox) * matrix)
        origin, tip = fitz.Point(0, 0) * matrix, fitz.Point(direction) * matrix
        direction = (tip.x - origin.x, tip.y - origin.y)
    return bbox, direction


def page_lines(page: fitz.Page) -> list[dict]:
    from_ocr = not page_has_text_layer(page)
    text_dict = ocr_page_dict(page) if from_ocr else page.get_text("dict")
    out = []
    for block in text_dict["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"])
            if not text.strip():
                continue
            bbox, direction = _visual_line(line, page)
            entry = {
                "text": text.strip(),
                "bbox": tuple(round(v, 1) for v in bbox),
                "size": round(line["spans"][0]["size"], 1),
                "dir": tuple(round(v) for v in direction),
            }
            if from_ocr:
                entry["ocr"] = True
            out.append(entry)
    return out


def _sheet_number(lines: list[dict], width: float, height: float) -> str | None:
    sheet, best = None, 0.0
    for ln in lines:
        text = ln["text"].strip()
        in_title_block = ln["bbox"][0] > width * 0.8 and ln["bbox"][1] > height * 0.8
        if RE_SHEET.match(text) and ln["size"] > best and in_title_block:
            best, sheet = ln["size"], text
    if sheet and not sheet.startswith("S-"):
        sheet = "S-" + sheet[1:]
    return sheet


def _under(anchor: dict, ln: dict) -> bool:
    x0, y1 = anchor["bbox"][0], anchor["bbox"][3]
    near = abs(ln["bbox"][0] - x0) < 40 and -4 <= ln["bbox"][1] - y1 < 40
    return near and ln["size"] >= 8 and ln is not anchor


def _title_block_title(lines: list[dict]) -> str | None:
    anchor = next((ln for ln in lines if norm_text(ln["text"]) == "TITRE DU DESSIN"), None)
    if anchor is None:
        return None
    below = sorted((ln for ln in lines if _under(anchor, ln)), key=lambda ln: ln["bbox"][1])
    return " ".join(ln["text"] for ln in below[:2]).strip() if below else None


def _drawing_titles(lines: list[dict]) -> list[str]:
    return [ln["text"] for ln in lines if ln["size"] >= 14 and RE_DRAWING_TITLE.search(norm_text(ln["text"]))]


def _series(sheet: str | None) -> str | None:
    return sheet[2] if sheet and len(sheet) >= 3 else None


def _plan_element_type(series: str | None, title: str | None) -> str | None:
    element_type = SERIES_TYPE.get(series) if series else None
    if element_type == "fondation" and not RE_FOUNDATION_TITLE.search(norm_text(title or "")):
        return None
    return element_type


def _plan_level(title: str | None, lines: list[dict]) -> str | None:
    return normalize_level(title) or next(
        (normalize_level(t) for t in _drawing_titles(lines) if normalize_level(t)), None
    )


def _plan_pages(project_dir: Path, pdf: Path) -> list[PageRef]:
    pages = []
    with fitz.open(pdf) as doc:
        for number, page in enumerate(doc, 1):
            lines = page_lines(page)
            width, height = page.rect.width, page.rect.height
            sheet, title = _sheet_number(lines, width, height), _title_block_title(lines)
            series = _series(sheet)
            pages.append(
                PageRef(
                    "plan",
                    pdf,
                    pdf.relative_to(project_dir).as_posix(),
                    number,
                    width,
                    height,
                    feuillet=sheet,
                    series=series,
                    type_element=_plan_element_type(series, title),
                    titre=title,
                    niveau=_plan_level(title, lines),
                    lines=lines,
                )
            )
    return pages


def _shop_pages(project_dir: Path, pdf: Path) -> list[PageRef]:
    category = pdf.parent.name
    element_type = next(
        (t for pattern, t in DA_CATEGORY_TYPE if re.search(pattern, norm_text(category))), None
    )
    with fitz.open(pdf) as doc:
        return [
            PageRef(
                "atelier",
                pdf,
                pdf.relative_to(project_dir).as_posix(),
                number,
                page.rect.width,
                page.rect.height,
                type_element=element_type,
                categorie=category,
                niveau=normalize_level(pdf.stem),
                lines=page_lines(page),
            )
            for number, page in enumerate(doc, 1)
        ]


def index_project(project_dir: Path) -> list[PageRef]:
    project_dir = Path(project_dir)
    plans, shops = plan_pdfs(project_dir), shop_pdfs(project_dir)
    pages = [page for pdf in plans for page in _plan_pages(project_dir, pdf)]
    prefetch_ocr([*plans, *shops])
    return pages + [page for pdf in shops for page in _shop_pages(project_dir, pdf)]
