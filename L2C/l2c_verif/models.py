from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ElementType = Literal["fondation", "poutre", "mur", "colonne", "dalle"]
Status = Literal["conforme", "non_conforme", "manquant_atelier", "ajoute_atelier"]
Method = Literal["regex", "table", "llm", "ocr"]


class Armature(BaseModel):
    repere: str | None = None
    diametre: str | None = None
    quantite: int | None = None
    espacement_mm: float | None = None
    longueur_mm: float | None = None
    role: str | None = None


class Item(BaseModel):
    id: str
    source: Literal["plan", "atelier"]
    fichier: str
    feuillet: str | None = None
    page: int
    x: float
    y: float
    type_element: ElementType
    element: str | None = None
    armature: list[Armature] = Field(default_factory=list)
    niveau: str | None = None
    localisation: str | None = None
    bbox: list[float] | None = None
    texte_brut: str | None = None
    confiance: float = 0.5
    methode: Method = "regex"
    localisation_note: str | None = None


class Ecart(BaseModel):
    attribut: str
    repere: str | None = None
    plan: str | None = None
    atelier: str | None = None


class Finding(BaseModel):
    id: str
    statut: Status
    type_element: ElementType
    element: str | None = None
    niveau: str | None = None
    feuillet: str | None = None
    plan_item: str | None = None
    atelier_item: str | None = None
    ecarts: list[Ecart] = Field(default_factory=list)
    confiance: float = 0.5
    note: str | None = None
