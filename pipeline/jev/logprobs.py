import math
import re
from typing import Any

Token = tuple[str, float, list[tuple[str, float]]]
JSON_TAIL = '",}]\n\r\t '


def value_offset(content: str, key: str) -> int | None:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"?', content)
    return match.end() if match else None


def covering_token(tokens: list[Token], offset: int) -> tuple[Token, int] | None:
    start = 0
    for token in tokens:
        end = start + len(token[0])
        if start <= offset < end:
            return token, start
        start = end
    return None


def alternatives_at(tokens: list[Token], content: str, offset: int) -> list[tuple[str, float]]:
    found = covering_token(tokens, offset)
    if found is None:
        return []
    token, start = found
    lead = content[start:offset]
    candidates = dict([*token[2], (token[0], token[1])])
    return [(text[len(lead) :], logprob) for text, logprob in candidates.items() if text.startswith(lead)]


def matching_option(text: str, options: list[str], chosen: str) -> str | None:
    stripped = text.rstrip(JSON_TAIL)
    if not stripped:
        return None
    matches = [option for option in options if option == stripped or option.startswith(stripped)]
    if len(matches) == 1:
        return matches[0]
    return chosen if chosen in matches else None


def option_probabilities(
    tokens: list[Token], content: str, key: str, options: list[str], chosen: str
) -> dict[str, float] | None:
    offset = value_offset(content, key)
    if offset is None:
        return None
    mass = dict.fromkeys(options, 0.0)
    for text, logprob in alternatives_at(tokens, content, offset):
        option = matching_option(text, options, chosen)
        if option is not None:
            mass[option] += math.exp(logprob)
    total = sum(mass.values())
    if total <= 0:
        return None
    return {option: round(value / total, 4) for option, value in mass.items()}


def compact_tokens(logprobs: list[dict[str, Any]] | None) -> list[Token]:
    return [
        (
            entry["token"],
            entry["logprob"],
            [
                (alternative["token"], alternative["logprob"])
                for alternative in entry.get("top_logprobs") or []
            ],
        )
        for entry in logprobs or []
    ]
