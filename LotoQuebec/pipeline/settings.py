import os
from datetime import timedelta, timezone
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
DATA = ROOT / "data"
CORPUS_DIR = DATA / "corpus" / "Projet360_NOVA_ETUDIANTS"
EVENTS_DIR = DATA / "events"
OUT = ROOT / "out"
CACHE = ROOT / "cache"
CONTENT = PACKAGE / "content"

MANIFEST_NAME = "MANIFEST.csv"
CORPUS_METADATA_FILES = frozenset({"README.txt", MANIFEST_NAME})

TIMEZONE = timezone(timedelta(hours=-4))
AS_OF = "2026-09-30T09:00:00-04:00"
DEFAULT_YEAR = 2026

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
DECISION_MODEL = os.environ.get("NOVA_DECISION_MODEL", "qwen3:8b")
VISION_MODEL = os.environ.get("NOVA_VISION_MODEL", "qwen2.5vl:7b")
EMBEDDING_MODEL = os.environ.get("NOVA_EMBEDDING_MODEL", "embeddinggemma")

JEV_API_KEY = os.environ.get("TYPESAFE_API_KEY")
JEV_URL = os.environ.get("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.environ.get("TYPESAFE_MODEL", "jev")
