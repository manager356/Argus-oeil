from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

from loeil import config, prompts


MODEL = "gemini-2.0-flash"
_FINALIZE_NAME = "finalize_interview"
_REQUIRED_ANSWER_KEYS = ("answer_1", "answer_2", "answer_3", "answer_4")


_client = genai.Client(api_key=config.GEMINI_API_KEY)


_finalize_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name=_FINALIZE_NAME,
            description=(
                "Appelle cette fonction UNIQUEMENT quand tu as obtenu les 4 réponses du candidat, "
                "dans l'ordre où elles ont été posées. N'envoie aucun message texte en parallèle de cet appel."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "answer_1": types.Schema(
                        type=types.Type.STRING,
                        description=f"Réponse à Q1 : {prompts.QUESTIONS[0]}",
                    ),
                    "answer_2": types.Schema(
                        type=types.Type.STRING,
                        description=f"Réponse à Q2 : {prompts.QUESTIONS[1]}",
                    ),
                    "answer_3": types.Schema(
                        type=types.Type.STRING,
                        description=f"Réponse à Q3 : {prompts.QUESTIONS[2]}",
                    ),
                    "answer_4": types.Schema(
                        type=types.Type.STRING,
                        description=f"Réponse à Q4 : {prompts.QUESTIONS[3]}",
                    ),
                },
                required=list(_REQUIRED_ANSWER_KEYS),
            ),
        )
    ]
)


_generation_config = types.GenerateContentConfig(
    system_instruction=prompts.SYSTEM_PROMPT,
    tools=[_finalize_tool],
    temperature=0.7,
)


@dataclass
class LLMResponse:
    text: str | None = None
    finalize: dict[str, str] | None = None

    @property
    def is_finalize(self) -> bool:
        return self.finalize is not None


def _extract_finalize(response: Any) -> dict[str, str] | None:
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        if content is None:
            continue
        for part in getattr(content, "parts", None) or []:
            fc = getattr(part, "function_call", None)
            if fc and getattr(fc, "name", None) == _FINALIZE_NAME:
                args = dict(getattr(fc, "args", None) or {})
                if all(k in args and args[k] for k in _REQUIRED_ANSWER_KEYS):
                    return {k: str(args[k]) for k in _REQUIRED_ANSWER_KEYS}
    return None


async def send_turn(history: list[dict]) -> LLMResponse:
    """Envoie l'historique de conversation à Gemini.

    Retourne :
      - LLMResponse(text=...) si Gemini envoie un message texte (à transmettre au candidat)
      - LLMResponse(finalize={answer_1: ..., answer_2: ..., answer_3: ..., answer_4: ...})
        si Gemini a appelé le tool finalize_interview avec les 4 réponses.
    """
    response = await _client.aio.models.generate_content(
        model=MODEL,
        contents=history,
        config=_generation_config,
    )

    finalize_args = _extract_finalize(response)
    if finalize_args is not None:
        return LLMResponse(finalize=finalize_args)

    text = (getattr(response, "text", None) or "").strip()
    return LLMResponse(text=text)
