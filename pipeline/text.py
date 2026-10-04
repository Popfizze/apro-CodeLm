import hashlib
import re
import unicodedata

TYPOGRAPHY = str.maketrans(
    {
        "’": "'",
        "‘": "'",
        "`": "'",
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "−": "-",
        "…": "...",
    }
)
ELLIPSIS = re.compile(r"\s*(?:\[\.\.\.\]|\(\.\.\.\)|\.\.\.)\s*")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(collapse_spaces(text).lower().encode("utf-8")).hexdigest()


def fingerprint(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def comparable(text: str) -> str:
    unified = unicodedata.normalize("NFKC", text).translate(TYPOGRAPHY)
    unified = unified.replace("**", "").replace(" | ", " ").replace('"', "")
    return collapse_spaces(unified).lower()


def quote_fragments(quote: str) -> list[str]:
    unified = unicodedata.normalize("NFKC", quote).translate(TYPOGRAPHY)
    return [comparable(part) for part in ELLIPSIS.split(unified) if comparable(part)]


def contains_quote(text: str, quote: str) -> bool:
    haystack = comparable(text)
    position = 0
    fragments = quote_fragments(quote)
    for fragment in fragments:
        found = haystack.find(fragment, position)
        if found < 0:
            return False
        position = found + len(fragment)
    return bool(fragments)
