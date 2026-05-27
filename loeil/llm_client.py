from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from loeil import config, prompts


MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1024
TEMPERATURE = 0.4

_FINALIZE_NAME = "finalize_interview"
_REQUIRED_ANSWER_KEYS = ("answer_1", "answer_2", "answer_3", "answer_4")
_REQUIRED_VERDICT_KEYS = ("niveau", "score", "tags", "synthese")
_REQUIRED_FINALIZE_KEYS = _REQUIRED_ANSWER_KEYS + _REQUIRED_VERDICT_KEYS


_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)


_finalize_tool: dict[str, Any] = {
    "name": _FINALIZE_NAME,
    "description": (
        "Appelle cette fonction quand tu as obtenu les 4 réponses ET formé un jugement clair. "
        "Remplis TOUS les champs, y compris le verdict. "
        "N'envoie aucun message texte en parallèle de cet appel."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "answer_1": {
                "type": "string",
                "description": f"Réponse à Q1 : {prompts.QUESTIONS[0]}",
            },
            "answer_2": {
                "type": "string",
                "description": f"Réponse à Q2 : {prompts.QUESTIONS[1]}",
            },
            "answer_3": {
                "type": "string",
                "description": f"Réponse à Q3 : {prompts.QUESTIONS[2]}",
            },
            "answer_4": {
                "type": "string",
                "description": f"Réponse à Q4 : {prompts.QUESTIONS[3]}",
            },
            "niveau": {
                "type": "string",
                "enum": ["PROFIL FORT", "À SURVEILLER", "REJETÉ"],
                "description": "Niveau du candidat selon ton jugement.",
            },
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10,
                "description": "Score entier de 0 à 10.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste de qualificatifs courts (ex: loyal, discret, vague, compétent).",
            },
            "synthese": {
                "type": "string",
                "description": "Jugement de L'Œil en 1 à 3 phrases, style froid et factuel.",
            },
        },
        "required": list(_REQUIRED_FINALIZE_KEYS),
    },
}


# Le system prompt est marqué pour le prompt caching d'Anthropic.
# Cache TTL de 5 min — économise des tokens sur les tours successifs d'un même entretien.
_system_blocks: list[dict[str, Any]] = [
    {
        "type": "text",
        "text": prompts.SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]


@dataclass
class LLMResponse:
    text: str | None = None
    finalize: dict[str, Any] | None = None

    @property
    def is_finalize(self) -> bool:
        return self.finalize is not None


def _extract_finalize(response: Any) -> dict[str, Any] | None:
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == _FINALIZE_NAME:
            args = dict(getattr(block, "input", None) or {})
            # Réponses aux 4 questions obligatoires (non vides)
            if not all(k in args and args[k] for k in _REQUIRED_ANSWER_KEYS):
                return None
            # Tous les champs verdict présents
            if not all(k in args for k in _REQUIRED_VERDICT_KEYS):
                return None
            # niveau et synthese doivent être non vides (score peut être 0, tags peut être [])
            if not args.get("niveau") or not args.get("synthese"):
                return None
            # niveau doit appartenir à l'enum défini dans le JSON schema
            if args["niveau"] not in ("PROFIL FORT", "À SURVEILLER", "REJETÉ"):
                return None
            # Sécurisation du cast : null ou valeur non entière → rejet
            try:
                score_int = int(args["score"])
            except (TypeError, ValueError):
                return None
            return {
                **{k: str(args[k]) for k in _REQUIRED_ANSWER_KEYS},
                "niveau": str(args["niveau"]),
                "score": score_int,
                "tags": list(args["tags"]) if isinstance(args["tags"], list) else [],
                "synthese": str(args["synthese"]),
            }
    return None


def _extract_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


async def send_turn(history: list[dict]) -> LLMResponse:
    """Envoie l'historique de conversation à Claude.

    Retourne :
      - LLMResponse(text=...) si Claude envoie un message texte (à transmettre au candidat)
      - LLMResponse(finalize={answer_1: ..., answer_2: ..., answer_3: ..., answer_4: ...,
                              niveau: ..., score: ..., tags: [...], synthese: ...})
        si Claude a appelé l'outil finalize_interview avec toutes les réponses et le verdict.
    """
    response = await _client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=_system_blocks,
        tools=[_finalize_tool],
        messages=history,
    )

    finalize_args = _extract_finalize(response)
    if finalize_args is not None:
        return LLMResponse(finalize=finalize_args)

    return LLMResponse(text=_extract_text(response))
