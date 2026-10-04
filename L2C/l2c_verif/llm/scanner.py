from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

from ..blocks import Block
from ..rebar import norm_text
from . import client
from .client import DEFAULT_MODEL
from .grounding import to_armature, ungrounded_values
from .schema import JSON_SCHEMA, SYSTEM_PROMPT, LlmBatch, parse_validate

log = logging.getLogger("l2c_verif.llm")

Items = list[tuple[str, str, str]]
Answer = tuple[LlmBatch, dict[str, list[str]]]
COUNTERS = (
    "batches",
    "cache_hits",
    "calls",
    "seconds",
    "retries",
    "failures",
    "unique_blocks",
    "valid_json_first_try",
    "ungrounded_retries",
    "ungrounded_values",
    "cached_seconds",
)
FLOAT_COUNTERS = {"seconds", "cached_seconds"}


def _cache_path(cache_dir: Path, payload: dict) -> Path:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return cache_dir / f"{digest}.json"


def _cache_key(payload: dict) -> dict:
    return {**payload, "options": {k: v for k, v in payload["options"].items() if k != "num_predict"}}


def _context_of(block: Block) -> str:
    page = block.page
    parts = [f"source={'plan' if page.source == 'plan' else 'shop drawing'}"]
    if page.feuillet:
        parts.append(f"sheet={page.feuillet}")
    if page.titre:
        parts.append(f"title={norm_text(page.titre)}")
    if page.categorie:
        parts.append(f"category={norm_text(page.categorie)}")
    if page.type_element:
        parts.append(f"element_type={page.type_element}")
    return ", ".join(parts)


def _block_payload_text(block: Block, keep: list[int] | None = None) -> str:
    if block.kind == "table_row":
        return f"TABLE HEADER: {block.meta['header']}\nROW: {' | '.join(block.meta['cells'])}"
    texts = block.texts if keep is None else [block.texts[i] for i in keep]
    return "\n".join(texts)


def _total_failures(bad: dict[str, list[str]]) -> int:
    return sum(len(v) for v in bad.values())


class LlmScanner:
    def __init__(
        self, cache_dir: Path, model: str = DEFAULT_MODEL, batch_size: int = 5, refresh: bool = False
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.batch_size = batch_size
        self.refresh = refresh
        self.stats = {name: 0.0 if name in FLOAT_COUNTERS else 0 for name in COUNTERS}
        self.stats["batch_size"] = batch_size
        self.batch_seconds: list[float] = []

    def _request(self, items: Items) -> dict:
        body = "\n\n".join(f"### id={uid}\ncontext: {ctx}\ntext:\n{txt}" for uid, ctx, txt in items)
        user = f"/no_think\nExtract the rebar of each snippet below. Answer in JSON.\n\n{body}"
        lines = sum(len(txt.splitlines()) for _, _, txt in items)
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
            "format": JSON_SCHEMA,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0,
                "num_ctx": 8192,
                "seed": 0,
                "num_predict": min(6000, 300 * len(items) + 120 * lines),
            },
        }

    def _ungrounded(self, data: LlmBatch, items: Items) -> dict[str, list[str]]:
        texts = {uid: txt for uid, _, txt in items}
        out = {}
        for block in data.blocks:
            bad = ungrounded_values(block, texts[block.id]) if block.id in texts else []
            if bad:
                out[block.id] = bad
        return out

    def _read_cache(self, path: Path, ids: list[str], items: Items) -> Answer | None:
        self.stats["cache_hits"] += 1
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            data = parse_validate(cached["content"], ids)
            if cached.get("first_try_valid", True):
                self.stats["valid_json_first_try"] += 1
            self.stats["cached_seconds"] = round(self.stats["cached_seconds"] + cached.get("seconds", 0.0), 2)
            self.stats["retries"] += cached.get("retries", 0)
            bad = self._ungrounded(data, items)
            self.stats["ungrounded_values"] += _total_failures(bad)
        except Exception as exc:
            log.warning("ignoring unreadable LLM cache entry %s: %s", path.name, exc)
            return None
        return data, bad

    def _ask(self, payload: dict, messages: list[dict]) -> str:
        content = client.chat({**payload, "messages": messages})["message"]["content"]
        self.stats["calls"] += 1
        return content

    def _first_answer(
        self, payload: dict, messages: list[dict], ids: list[str]
    ) -> tuple[LlmBatch, str, bool]:
        content = self._ask(payload, messages)
        try:
            return parse_validate(content, ids), content, True
        except ValueError as exc:
            retry = (
                f"/no_think\nYour answer was invalid: {str(exc)[:500]}. "
                "Answer again with valid JSON covering every id."
            )
            messages += [{"role": "assistant", "content": content}, {"role": "user", "content": retry}]
            content = self._ask(payload, messages)
            return parse_validate(content, ids), content, False

    def _regrounded(self, payload: dict, messages: list[dict], items: Items, answer: tuple) -> tuple:
        data, bad, content = answer
        self.stats["ungrounded_retries"] += 1
        cite = "; ".join(f"id={k}: {', '.join(v)}" for k, v in bad.items())
        retry = (
            f"/no_think\nThese values are not written on one single line of the snippet: {cite[:1500]}. "
            "Only report values literally written, each bar from one line. Answer again for every id."
        )
        messages += [{"role": "assistant", "content": content}, {"role": "user", "content": retry}]
        second = self._ask(payload, messages)
        try:
            second_data = parse_validate(second, [uid for uid, _, _ in items])
            second_bad = self._ungrounded(second_data, items)
        except ValueError:
            return answer
        if _total_failures(second_bad) <= _total_failures(bad):
            return second_data, second_bad, second
        return answer

    def _query(self, payload: dict, ids: list[str], items: Items) -> tuple:
        messages = list(payload["messages"])
        data, content, first_try = self._first_answer(payload, messages, ids)
        bad = self._ungrounded(data, items)
        if bad and first_try:
            data, bad, content = self._regrounded(payload, messages, items, (data, bad, content))
            return data, bad, content, first_try, 1
        return data, bad, content, first_try, 0 if first_try else 1

    def _record(self, seconds: float, first_try: bool, retries: int, bad: dict, size: int) -> None:
        self.stats["seconds"] += seconds
        self.stats["retries"] += retries
        self.stats["valid_json_first_try"] += int(first_try)
        self.stats["ungrounded_values"] += _total_failures(bad)
        self.batch_seconds.append(round(seconds, 1))
        log.info("LLM batch of %d blocks: %.1fs (%.2fs/block)", size, seconds, seconds / max(size, 1))

    def _run_batch(self, items: Items) -> Answer | None:
        payload = self._request(items)
        ids = [uid for uid, _, _ in items]
        path = _cache_path(self.cache_dir, _cache_key(payload))
        if path.exists() and not self.refresh:
            cached = self._read_cache(path, ids, items)
            if cached is not None:
                return cached
        started = time.time()
        try:
            data, bad, content, first_try, retries = self._query(payload, ids, items)
        except Exception as exc:
            self.stats["failures"] += 1
            log.warning("LLM batch failed (%d blocks): %s", len(items), exc)
            return None
        seconds = time.time() - started
        self._record(seconds, first_try, retries, bad, len(items))
        entry = {
            "model": self.model,
            "content": content,
            "seconds": round(seconds, 2),
            "first_try_valid": first_try,
            "retries": retries,
        }
        path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        return data, bad

    def _log_throughput(self, batches: int) -> None:
        average = sum(self.batch_seconds) / len(self.batch_seconds)
        log.info(
            "LLM throughput: %.1fs/batch -> projected %.1f min for %d batches",
            average,
            average * batches / 60,
            batches,
        )

    def scan(
        self, blocks: list[Block], line_filter: Callable[[Block], list[int]] | None = None
    ) -> dict[str, dict]:
        unique: dict[tuple[str, str], list[Block]] = {}
        for block in blocks:
            key = (
                _context_of(block),
                _block_payload_text(block, line_filter(block) if line_filter else None),
            )
            unique.setdefault(key, []).append(block)
        keys = list(unique)
        self.stats["unique_blocks"] = len(keys)
        out: dict[str, dict] = {}
        batches = (len(keys) + self.batch_size - 1) // self.batch_size
        for index, start in enumerate(range(0, len(keys), self.batch_size)):
            chunk = keys[start : start + self.batch_size]
            items = [(f"u{start + k}", ctx, txt) for k, (ctx, txt) in enumerate(chunk)]
            self.stats["batches"] += 1
            answer = self._run_batch(items)
            if index == 2 and self.batch_seconds:
                self._log_throughput(batches)
            if answer is not None:
                self._collect(answer, items, [unique[key] for key in chunk], out)
        return out

    @staticmethod
    def _collect(answer: Answer, items: Items, groups: list[list[Block]], out: dict[str, dict]) -> None:
        data, bad = answer
        by_id = {block.id: block for block in data.blocks}
        for (uid, _, _), group in zip(items, groups, strict=True):
            reading = by_id.get(uid)
            if reading is None:
                continue
            bars = [a for a in (to_armature(x) for x in reading.barres) if a is not None]
            for block in group:
                out[block.id] = {
                    "armature": bars,
                    "localisation": reading.localisation,
                    "type_element": reading.type_element,
                    "ungrounded": bad.get(uid, []),
                    "raw": reading.model_dump(),
                }
