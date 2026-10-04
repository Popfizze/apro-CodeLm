from pathlib import Path

from pipeline.jsonio import read_json
from pipeline.records import Passage, Questions

DEFINITIONS = read_json(Path(__file__).with_name("contract.json"))
PASSAGE_QUESTIONS: Questions = DEFINITIONS["passage"]
PAIR_QUESTIONS: Questions = DEFINITIONS["pair"]
SUBJECTS: dict[str, str] = PASSAGE_QUESTIONS["subject"]["criteria"]


def passage_state(passage: Passage) -> str:
    return (
        f"Source : {passage['source_id']} ({passage['kind']}), fichier : {passage['path']}, "
        f"repère : {passage['locator']}\n"
        f"Date : {passage['date'] or 'inconnue'} | Auteur : {passage['author'] or 'inconnu'}\n"
        f"Texte :\n{passage['text']}"
    )


def statement(label: str, passage: Passage) -> str:
    return (
        f"ÉNONCÉ {label} — source {passage['source_id']} ({passage['kind']}), fichier {passage['path']}, "
        f"repère {passage['locator']}, "
        f"date {passage['date'] or 'inconnue'}, auteur {passage['author'] or 'inconnu'} :\n{passage['text']}"
    )


def pair_state(first: Passage, second: Passage) -> str:
    return f"{statement('A', first)}\n\n{statement('B', second)}"
