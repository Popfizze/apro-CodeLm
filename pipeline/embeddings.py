import base64
import math
import struct
from pathlib import Path
from typing import Any

from pipeline.cache import DiskCache
from pipeline.ollama import embed
from pipeline.records import Passage
from pipeline.settings import EMBEDDING_MODEL
from pipeline.text import fingerprint

DOCUMENT_TEMPLATE = "title: {title} | text: {text}"
QUERY_TEMPLATE = "task: search result | query: {text}"
BATCH_SIZE = 16
INT8_LIMIT = 127


def document_input(passage: Passage) -> str:
    title = Path(passage["path"]).stem.replace("_", " ")
    return DOCUMENT_TEMPLATE.format(title=title, text=passage["text"])


def pack_floats(values: list[float]) -> str:
    return base64.b64encode(struct.pack(f"<{len(values)}f", *values)).decode("ascii")


def unpack_floats(encoded: str) -> list[float]:
    data = base64.b64decode(encoded)
    return list(struct.unpack(f"<{len(data) // 4}f", data))


def normalized(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def quantized(vector: list[float]) -> tuple[bytes, float]:
    scale = max(abs(value) for value in vector) / INT8_LIMIT or 1.0
    levels = [max(-INT8_LIMIT, min(INT8_LIMIT, round(value / scale))) for value in vector]
    return struct.pack(f"<{len(levels)}b", *levels), scale


class Embedder:
    def __init__(self, model: str = EMBEDDING_MODEL) -> None:
        self.model = model
        self.cache = DiskCache("embeddings")

    def key(self, text: str) -> str:
        return fingerprint(self.model, text)

    def fill_cache(self, texts: list[str]) -> None:
        missing = list(dict.fromkeys(text for text in texts if self.cache.get(self.key(text)) is None))
        for start in range(0, len(missing), BATCH_SIZE):
            batch = missing[start : start + BATCH_SIZE]
            for text, vector in zip(batch, embed(self.model, batch), strict=True):
                self.cache.put(self.key(text), pack_floats(normalized(vector)))

    def vectors(self, texts: list[str]) -> list[list[float]]:
        self.fill_cache(texts)
        return [unpack_floats(self.cache.get(self.key(text))) for text in texts]


def embedding_index(passages: list[Passage], embedder: Embedder | None = None) -> dict[str, Any]:
    model = embedder or Embedder()
    vectors = model.vectors([document_input(passage) for passage in passages])
    packed = [quantized(vector) for vector in vectors]
    return {
        "model": model.model,
        "dimension": len(vectors[0]) if vectors else 0,
        "count": len(vectors),
        "encoding": "int8",
        "normalized": True,
        "similarity": "cosine = scale[i] * dot(int8_vector[i], unit_query_vector)",
        "document_template": DOCUMENT_TEMPLATE,
        "query_template": QUERY_TEMPLATE,
        "ids": [passage["id"] for passage in passages],
        "scales": pack_floats([scale for _, scale in packed]),
        "vectors": base64.b64encode(b"".join(data for data, _ in packed)).decode("ascii"),
    }
