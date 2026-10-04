import json
from pathlib import Path
from typing import Any

from pipeline.settings import CACHE


class DiskCache:
    def __init__(self, name: str, directory: Path = CACHE) -> None:
        self.path = directory / f"{name}.jsonl"
        self.entries: dict[str, Any] = {}
        if self.path.exists():
            self.entries = dict(self._load())

    def _load(self) -> list[tuple[str, Any]]:
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines if line.strip()]
        return [(record["key"], record["value"]) for record in records]

    def get(self, key: str) -> Any:
        return self.entries.get(key)

    def put(self, key: str, value: Any) -> None:
        self.entries[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")
