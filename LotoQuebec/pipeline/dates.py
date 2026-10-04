import re
from datetime import date, datetime

from pipeline.settings import DEFAULT_YEAR, TIMEZONE
from pipeline.text import strip_accents

MONTHS = {
    "janvier": 1,
    "janv": 1,
    "fevrier": 2,
    "fevr": 2,
    "fev": 2,
    "mars": 3,
    "avril": 4,
    "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "juil": 7,
    "aout": 8,
    "septembre": 9,
    "sept": 9,
    "octobre": 10,
    "oct": 10,
    "novembre": 11,
    "nov": 11,
    "decembre": 12,
    "dec": 12,
}
FRENCH_DATE = re.compile(
    r"\b(\d{1,2})(?:er)?\s+([A-Za-zéûÉÛ]+)\.?(?:\s+(\d{4}))?(?:[ \t]*(?:-|à)?[ \t]*(\d{1,2})[:h](\d{2}))?",
    re.IGNORECASE,
)
ISO_DATE = re.compile(r"\b(\d{4})[-.](\d{2})[-.](\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?")
DAY_MONTH = re.compile(r"(\d{1,2})([A-Za-zéû]+)$")


def to_iso(year: object, month: object, day: object, hour: object = None, minute: object = None) -> str:
    if hour is None or minute is None:
        return date(int(str(year)), int(str(month)), int(str(day))).isoformat()
    moment = datetime(
        int(str(year)), int(str(month)), int(str(day)), int(str(hour)), int(str(minute)), tzinfo=TIMEZONE
    )
    return moment.isoformat()


def month_number(word: str) -> int | None:
    return MONTHS.get(strip_accents(word).lower())


def first_french_date(text: str, default_year: int) -> tuple[int, str] | None:
    for match in FRENCH_DATE.finditer(text):
        month = month_number(match.group(2))
        if month:
            year = match.group(3) or default_year
            return match.start(), to_iso(year, month, match.group(1), match.group(4), match.group(5))
    return None


def first_iso_date(text: str) -> tuple[int, str] | None:
    match = ISO_DATE.search(text)
    if not match:
        return None
    year, month, day, hour, minute = match.group(1, 2, 3, 4, 5)
    return match.start(), to_iso(year, month, day, hour, minute)


def find_date(text: str, default_year: int = DEFAULT_YEAR) -> str | None:
    hits = [hit for hit in (first_french_date(text, default_year), first_iso_date(text)) if hit]
    return min(hits)[1] if hits else None


def with_time(day_iso: str, hours_minutes: str) -> str:
    year, month, day = day_iso[:10].split("-")
    hour, minute = hours_minutes.split(":")
    return to_iso(year, month, day, hour, minute)


def date_from_file_stem(stem: str, default_year: int = DEFAULT_YEAR) -> str | None:
    tail = stem.rsplit("_", maxsplit=1)[-1]
    day_month = DAY_MONTH.match(tail)
    if day_month and month_number(day_month.group(2)):
        return to_iso(default_year, month_number(day_month.group(2)), day_month.group(1))
    month = month_number(tail)
    return f"{default_year}-{month:02d}" if month else None


def days_between(first: str | None, second: str | None) -> int | None:
    try:
        start = datetime.fromisoformat((first or "")[:10])
        end = datetime.fromisoformat((second or "")[:10])
    except ValueError:
        return None
    return (start - end).days
