from __future__ import annotations

import http.client
import json
import logging

log = logging.getLogger("l2c_verif.llm")

OLLAMA_HOST = "localhost"
OLLAMA_PORT = 11434
DEFAULT_MODEL = "qwen3:8b"


def _call(method: str, path: str, payload: dict | None = None, timeout: float = 600.0) -> bytes:
    connection = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=timeout)
    try:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        data = response.read()
    finally:
        connection.close()
    if response.status != 200:
        raise OSError(f"Ollama {path} answered HTTP {response.status}")
    return data


def ollama_available(timeout: float = 3.0) -> bool:
    try:
        _call("GET", "/api/tags", timeout=timeout)
    except Exception:
        return False
    return True


def chat(payload: dict, timeout: float = 600.0) -> dict:
    return json.loads(_call("POST", "/api/chat", payload, timeout).decode("utf-8"))


def unload_model(model: str = DEFAULT_MODEL) -> None:
    try:
        _call("POST", "/api/generate", {"model": model, "keep_alive": 0}, timeout=30)
    except Exception as exc:
        log.warning("could not unload %s: %s", model, exc)
