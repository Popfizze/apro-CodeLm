import json
import urllib.error
import urllib.request
from typing import Any

from pipeline.settings import OLLAMA_URL


class OllamaUnavailableError(Exception):
    pass


def post(endpoint: str, body: dict[str, Any], timeout: float = 900) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{OLLAMA_URL}{endpoint}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read()[:300].decode("utf-8", "replace")
        raise OllamaUnavailableError(f"Ollama {endpoint} HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        raise OllamaUnavailableError(f"Ollama is not reachable at {OLLAMA_URL}: {error}") from error
    return payload


def chat_json(
    model: str,
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    options: dict[str, Any],
    top_logprobs: int = 0,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "format": schema,
        "think": False,
        "stream": False,
        "options": options,
    }
    if top_logprobs:
        body["logprobs"] = True
        body["top_logprobs"] = top_logprobs
    return post("/api/chat", body)


def embed(model: str, texts: list[str]) -> list[list[float]]:
    response = post("/api/embed", {"model": model, "input": texts})
    vectors: list[list[float]] = response["embeddings"]
    return vectors


def is_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/version", timeout=3) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False
