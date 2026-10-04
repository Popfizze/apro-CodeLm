from __future__ import annotations

from pydantic import BaseModel


class LlmBar(BaseModel):
    role: str = ""
    diametre: str = ""
    quantite: int | None = None
    espacement: str = ""
    repere: str = ""
    longueur: str = ""


class LlmBlock(BaseModel):
    id: str
    type_element: str = ""
    localisation: str = ""
    barres: list[LlmBar] = []


class LlmBatch(BaseModel):
    blocks: list[LlmBlock]


JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type_element": {
                        "type": "string",
                        "enum": ["fondation", "colonne", "poutre", "mur", "dalle", "autre"],
                    },
                    "localisation": {"type": "string"},
                    "barres": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "diametre": {"type": "string"},
                                "quantite": {"type": ["integer", "null"]},
                                "espacement": {"type": "string"},
                                "repere": {"type": "string"},
                                "longueur": {"type": "string"},
                            },
                            "required": ["role", "diametre", "quantite", "espacement", "repere", "longueur"],
                        },
                    },
                },
                "required": ["id", "type_element", "localisation", "barres"],
            },
        }
    },
    "required": ["blocks"],
}

SYSTEM_PROMPT = """You read text snippets extracted from Quebec structural concrete drawings (plans) and \
rebar shop drawings (dessins d'atelier). For each snippet, extract every reinforcing bar specification.

Rules:
- diametre: Canadian metric bar size exactly as written: 10M, 15M, 20M, 25M, 30M, 35M.
- quantite: number of bars if given, else null. "3-20M" -> 3. "LONG: 9 20M 20U10-06" -> 9. \
"12(6)-15M" -> 12. Never use the bar size as a count: "10M@6\\" c/c" has no count (null).
- espacement: the raw spacing text after "@" without "c/c" (e.g. "6\\"", "12\\"", "300"), else "".
- repere: the shop bending mark if present (e.g. "20U10-06", "30Z9-08", "10ET11X17"), else "".
- longueur: raw length text if a bar length is written, else "".
- role: the bar role label: "ARM." on column callouts -> "VERT"; "VERT" -> "VERT"; "LIG." or "ETRI"/"ÉTRI" \
(ties/stirrups) -> "LIG"; "LONG" -> "LONG"; "TRAN"/"TRANS" -> "TRAN"; "GOUJ" -> "GOUJ"; "ATT" -> "ATT"; \
"RANG 2" -> "RANG 2"; integrity bars "12(6)" -> "INTEG". For table rows, take the role from the column \
header ("ARM. LONG." -> "LONG", "ARM. TRANS." -> "TRAN").
- localisation: a grid location written in the text (e.g. "COLONNE C-4" -> "C-4"), else "".
- type_element: fondation, colonne, poutre, mur, dalle or autre, using the snippet and its context.
- Each bar entry comes from ONE text line: its size, count, spacing and mark are all written on that line. \
Snippets are independent: never copy values from one snippet to another.
- Never invent bars that are not written. Return exactly one entry per input id, with the same id."""


def parse_validate(content: str, expected_ids: list[str]) -> LlmBatch:
    data = LlmBatch.model_validate_json(content)
    received = {block.id for block in data.blocks}
    missing = [i for i in expected_ids if i not in received]
    if missing:
        raise ValueError(f"missing ids in response: {missing}")
    return data
