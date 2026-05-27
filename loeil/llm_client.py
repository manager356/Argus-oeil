from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from loeil import config, prompts


MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1024
TEMPERATURE = 0.4

_FINALIZE_NAME = "finalize_interview"
_REQUIRED_ANSWER_KEYS = ("answer_1", "answer_2", "answer_3", "answer_4")


_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)


_finalize_tool: dict[str, Any] = {
    "name": _FINALIZE_NAME,
    "description": (
        "Appelle cette fonction UNIQUEMENT quand tu as obtenu les 4 réponses du candidat, "
        "dans l'ordre où elles ont été posées. N'envoie aucun message texte en parallèle de cet appel."
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
        },
        "required": list(_REQUIRED_ANSWER_KEYS),
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
    finalize: dict[str, str] | None = None

    @property
    def is_finalize(self) -> bool:
        return self.finalize is not None


def _extract_finalize(response: Any) -> dict[str, str] | None:
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == _FINALIZE_NAME:
            args = dict(getattr(block, "input", None) or {})
            if all(k in args and args[k] for k in _REQUIRED_ANSWER_KEYS):
                return {k: str(args[k]) for k in _REQUIRED_ANSWER_KEYS}
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
      - LLMResponse(finalize={answer_1: ..., answer_2: ..., answer_3: ..., answer_4: ...})
        si Claude a appelé l'outil finalize_interview avec les 4 réponses.
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
