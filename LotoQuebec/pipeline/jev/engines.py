import json
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

from pipeline.cache import DiskCache
from pipeline.jev.answers import as_option, build_answer, options_of, schema_of
from pipeline.jev.logprobs import compact_tokens, option_probabilities
from pipeline.ollama import chat_json
from pipeline.records import Answers, Questions
from pipeline.settings import DECISION_MODEL, JEV_API_KEY, JEV_MODEL, JEV_URL
from pipeline.text import fingerprint

CONTEXT_SIZE = 8192
TOP_LOGPROBS = 10
OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": CONTEXT_SIZE}
RETRYABLE_STATUS = {429, 500, 502, 503}
TYPE_LABELS = {"choice": "choix d'une clé", "score": "score entier", "noul": "vrai ou faux"}
PREAMBLE = (
    "Tu lis un extrait daté et sourcé du corpus du projet NOVA (portail, phase 1) pour alimenter "
    "une mémoire de projet. Date de référence : 30 septembre 2026, 09:00, heure de Montréal.\n"
    "Réponds à chaque question d'après l'extrait seul, au format JSON demandé.\n"
    "Règles de lecture : une proposition n'est pas une décision ; un correctif annoncé n'est pas une "
    "validation ; une date de fichier récente ne garantit pas une information exacte ; salutations, "
    "signatures et contenus hors projet sont du bruit.\n"
    "Commence par « analyse » : une phrase courte qui dit qui s'exprime, sur quoi, et si l'extrait "
    "propose, décide, approuve, valide, livre, constate, engage, alerte, change un responsable, facture, "
    "règle un paiement, informe ou n'apporte rien au projet."
)
ANALYSIS_KEY = "analyse"


class JevEngine(Protocol):
    name: str
    model: str | None

    def ask(self, state: str, questions: Questions) -> Answers: ...


def criteria_lines(question: dict[str, Any]) -> list[str]:
    criteria = question["criteria"]
    if question["type"] == "score":
        return [f"  - {level} : {label}" for level, label in enumerate(criteria)]
    if question["type"] == "noul":
        return [f"  - true : {criteria['true']}", f"  - false : {criteria['false']}"]
    return [f"  - {key} : {label}" for key, label in criteria.items()]


def system_prompt(questions: Questions) -> str:
    lines = [PREAMBLE, "", "Questions :"]
    for key, question in questions.items():
        lines.append(f"[{key}] ({TYPE_LABELS[question['type']]}) {question['instructions']}")
        lines.extend(criteria_lines(question))
    return "\n".join(lines)


def answer_schema(questions: Questions) -> dict[str, Any]:
    properties = {key: schema_of(question) for key, question in questions.items()}
    return {
        "type": "object",
        "properties": {ANALYSIS_KEY: {"type": "string"}, **properties},
        "required": [ANALYSIS_KEY, *questions],
    }


class LocalJevEngine:
    def __init__(self, model: str = DECISION_MODEL) -> None:
        self.model: str | None = model
        self.name = f"local:{model}"
        self.cache = DiskCache("decisions")
        self.queries = 0

    def ask(self, state: str, questions: Questions) -> Answers:
        prompt = system_prompt(questions)
        key = fingerprint(self.name, prompt, json.dumps(answer_schema(questions), sort_keys=True), state)
        reply = self.cache.get(key)
        if reply is None:
            reply = self.query(prompt, state, questions)
            self.cache.put(key, reply)
        return self.answers(reply, questions)

    def query(self, prompt: str, state: str, questions: Questions) -> dict[str, Any]:
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": state}]
        response = chat_json(str(self.model), messages, answer_schema(questions), OPTIONS, TOP_LOGPROBS)
        if response.get("prompt_eval_count", 0) >= CONTEXT_SIZE:
            raise ValueError("decision prompt exceeds the context window")
        self.queries += 1
        return {"content": response["message"]["content"], "tokens": compact_tokens(response.get("logprobs"))}

    def answers(self, reply: dict[str, Any], questions: Questions) -> Answers:
        content, tokens = reply["content"], reply["tokens"]
        values = json.loads(content)
        result: Answers = {}
        for key, question in questions.items():
            chosen = as_option(values[key])
            options = options_of(question)
            probabilities = option_probabilities(tokens, content, key, options, chosen) if tokens else None
            result[key] = build_answer(question, chosen, probabilities, self.name)
        return result


class TypesafeJevEngine:
    def __init__(self, api_key: str, model: str = JEV_MODEL, url: str = JEV_URL, retries: int = 3) -> None:
        self.api_key, self.url, self.retries = api_key, url, retries
        self.requested_model = model
        self.model: str | None = model
        self.name = "jev"
        self.cache = DiskCache("jev")

    def ask(self, state: str, questions: Questions) -> Answers:
        key = fingerprint(self.name, self.requested_model, json.dumps(questions, sort_keys=True), state)
        answers: Answers | None = self.cache.get(key)
        if answers is None:
            answers = self.query(state, questions)
            self.cache.put(key, answers)
        return answers

    def request(self, state: str, questions: Questions) -> urllib.request.Request:
        payload = {"state": state, "model": self.requested_model, "questions": questions}
        body = json.dumps(payload).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        return urllib.request.Request(self.url, data=body, method="POST", headers=headers)

    def query(self, state: str, questions: Questions) -> Answers:
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(self.request(state, questions), timeout=60) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code not in RETRYABLE_STATUS or attempt == self.retries - 1:
                    raise RuntimeError(f"JEV HTTP {error.code}: {error.read()[:300]!r}") from error
                time.sleep(2**attempt)
                continue
            self.model = data.get("model", self.model)
            return {key: {**answer, "engine": self.name} for key, answer in data["answers"].items()}
        raise RuntimeError("JEV did not answer")


def select_engine() -> JevEngine:
    return TypesafeJevEngine(JEV_API_KEY) if JEV_API_KEY else LocalJevEngine()
