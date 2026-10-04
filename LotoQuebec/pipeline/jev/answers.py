from typing import Any

from pipeline.records import Answer, Question

NOUL_OPTIONS = ["true", "false"]


def options_of(question: Question) -> list[str]:
    if question["type"] == "choice":
        return list(question["criteria"])
    if question["type"] == "score":
        return [str(level) for level in range(len(question["criteria"]))]
    return NOUL_OPTIONS


def schema_of(question: Question) -> dict[str, Any]:
    if question["type"] == "choice":
        return {"type": "string", "enum": list(question["criteria"])}
    if question["type"] == "score":
        return {"type": "integer", "enum": list(range(len(question["criteria"])))}
    return {"type": "boolean"}


def as_option(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def confidence(probabilities: dict[str, float] | None) -> float | None:
    return max(probabilities.values()) if probabilities else None


def noul_answer(value: str, probabilities: dict[str, float] | None) -> Answer:
    probability = probabilities["true"] if probabilities else float(value == "true")
    return {"type": "noul", "noul": probability}


def choice_answer(value: str, probabilities: dict[str, float] | None) -> Answer:
    return {
        "type": "choice",
        "choice": value,
        "probabilities": probabilities,
        "confidence": confidence(probabilities),
    }


def score_answer(value: str, probabilities: dict[str, float] | None) -> Answer:
    expected = sum(int(level) * share for level, share in probabilities.items()) if probabilities else None
    return {
        "type": "score",
        "score": round(expected, 4) if expected is not None else float(value),
        "probabilities": probabilities,
        "confidence": confidence(probabilities),
    }


BUILDERS = {"noul": noul_answer, "choice": choice_answer, "score": score_answer}


def build_answer(
    question: Question, value: Any, probabilities: dict[str, float] | None, engine: str
) -> Answer:
    answer = BUILDERS[question["type"]](as_option(value), probabilities)
    answer["engine"] = engine
    return answer


def answer_value(answer: Answer) -> Any:
    return answer.get(answer["type"])
