import csv
import hashlib
import re
from pathlib import Path

from pipeline.records import SourceRef
from pipeline.settings import CORPUS_DIR, CORPUS_METADATA_FILES, MANIFEST_NAME

FOLDER_KINDS = {
    "01_Courriels": "email",
    "02_Reunions": "meeting",
    "03_Tickets": "ticket",
    "04_Documents_projet": "project_doc",
    "05_Contrats_et_finances": "contract",
    "06_Architecture_et_decisions": "adr",
    "07_Conversations_Teams": "teams",
    "08_Archives_et_documents_connexes": "archive",
}
EXTENSION_KINDS = {".png": "image", ".csv": "csv"}
NUMBERED_SOURCE = re.compile(r"^([EM]\d{2})_")


class CorpusError(Exception):
    pass


def project_files(corpus_dir: Path = CORPUS_DIR) -> list[Path]:
    files = (path for path in corpus_dir.rglob("*") if path.is_file())
    return sorted(path for path in files if path.name not in CORPUS_METADATA_FILES)


def relative_path(path: Path, corpus_dir: Path = CORPUS_DIR) -> str:
    return path.relative_to(corpus_dir).as_posix()


def source_id_for(rel: str) -> str:
    stem = Path(rel).stem
    numbered = NUMBERED_SOURCE.match(stem)
    return numbered.group(1) if numbered else stem


def kind_for(rel: str) -> str:
    path = Path(rel)
    extension_kind = EXTENSION_KINDS.get(path.suffix.lower())
    if extension_kind:
        return extension_kind
    folder = path.parts[0] if len(path.parts) > 1 else ""
    kind = FOLDER_KINDS.get(folder, "archive")
    if kind == "contract" and path.stem.upper().startswith("INV-"):
        return "invoice"
    return kind


def source_ref(rel: str) -> SourceRef:
    return SourceRef(source_id_for(rel), rel, kind_for(rel))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_entries(corpus_dir: Path = CORPUS_DIR) -> dict[str, int]:
    with (corpus_dir / MANIFEST_NAME).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["fichier"]: int(row["taille_octets"])
        for row in rows
        if row["fichier"] not in CORPUS_METADATA_FILES
    }


def manifest_discrepancies(files: list[Path], corpus_dir: Path = CORPUS_DIR) -> list[str]:
    expected = manifest_entries(corpus_dir)
    found = {relative_path(path, corpus_dir): path.stat().st_size for path in files}
    missing = [f"missing from corpus: {name}" for name in sorted(set(expected) - set(found))]
    extra = [f"not in manifest: {name}" for name in sorted(set(found) - set(expected))]
    sizes = [
        f"size mismatch: {name} ({found[name]} != {expected[name]})"
        for name in sorted(set(found) & set(expected))
        if found[name] != expected[name]
    ]
    return missing + extra + sizes


def check_corpus(corpus_dir: Path = CORPUS_DIR) -> list[Path]:
    files = project_files(corpus_dir)
    problems = manifest_discrepancies(files, corpus_dir)
    if problems:
        raise CorpusError("corpus does not match its manifest:\n  " + "\n  ".join(problems))
    ids = [source_id_for(relative_path(path, corpus_dir)) for path in files]
    if len(ids) != len(set(ids)):
        raise CorpusError("two corpus files share the same source id")
    return files
