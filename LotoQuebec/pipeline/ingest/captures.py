import base64
import json
from typing import Any

from pipeline.cache import DiskCache
from pipeline.corpus import sha256_bytes
from pipeline.dates import find_date
from pipeline.ollama import chat_json
from pipeline.records import Passage, SourceRef, make_passage
from pipeline.settings import VISION_MODEL
from pipeline.text import fingerprint

PROMPT = (
    "Transcris le texte visible de cette capture d'écran, ligne visuelle par ligne visuelle, "
    "de haut en bas, mot pour mot, sans corriger, résumer, décrire ni traduire. "
    "Chaque rangée de tableau donne une seule ligne qui réunit toutes ses cellules, de gauche à droite, "
    "séparées par « — » ; l'en-tête du tableau donne aussi une seule ligne."
)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"lignes": {"type": "array", "items": {"type": "string"}}},
    "required": ["lignes"],
}
OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 6144}


class CaptureTranscriber:
    def __init__(self, model: str = VISION_MODEL) -> None:
        self.model = model
        self.cache = DiskCache("transcriptions")

    def lines(self, image: bytes) -> list[str]:
        key = fingerprint(self.model, PROMPT, json.dumps(SCHEMA, sort_keys=True), sha256_bytes(image))
        cached = self.cache.get(key)
        if cached is None:
            cached = self.transcribe(image)
            self.cache.put(key, cached)
        return list(cached)

    def transcribe(self, image: bytes) -> list[str]:
        message = {"role": "user", "content": PROMPT, "images": [base64.b64encode(image).decode("ascii")]}
        response = chat_json(self.model, [message], SCHEMA, OPTIONS)
        lines: list[str] = json.loads(response["message"]["content"])["lignes"]
        return [line.strip() for line in lines if line.strip()]


def capture_passages(
    source: SourceRef,
    image: bytes,
    transcriber: CaptureTranscriber,
    fallback_date: str | None,
    prefix: tuple[str, str] = ("", ""),
    **fields: Any,
) -> list[Passage]:
    locator_prefix, suffix_prefix = prefix
    lines = transcriber.lines(image)
    found = next((day for day in map(find_date, lines) if day), None)
    return [
        make_passage(
            source,
            f"{suffix_prefix}z{number}",
            f"{locator_prefix}capture : ligne {number}",
            line,
            date=found or fallback_date,
            **fields,
        )
        for number, line in enumerate(lines, start=1)
    ]
