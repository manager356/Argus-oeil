from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from loeil import llm_client


def _make_text_response(text: str) -> SimpleNamespace:
    """Imite la forme d'une réponse Gemini contenant uniquement du texte."""
    part = SimpleNamespace(function_call=None, text=text)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(candidates=[candidate], text=text)


def _make_function_call_response(name: str, args: dict) -> SimpleNamespace:
    """Imite la forme d'une réponse Gemini avec un function_call."""
    function_call = SimpleNamespace(name=name, args=args)
    part = SimpleNamespace(function_call=function_call, text=None)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(candidates=[candidate], text=None)


@pytest.mark.asyncio
async def test_send_turn_returns_text_when_no_function_call():
    fake_response = _make_text_response("Question 1.")
    with patch.object(llm_client._client.aio.models, "generate_content", new=AsyncMock(return_value=fake_response)):
        result = await llm_client.send_turn([{"role": "user", "parts": [{"text": "Bonjour"}]}])

    assert result.text == "Question 1."
    assert not result.is_finalize


@pytest.mark.asyncio
async def test_send_turn_returns_finalize_when_function_call_complete():
    args = {
        "answer_1": "réponse à Q1",
        "answer_2": "réponse à Q2",
        "answer_3": "réponse à Q3",
        "answer_4": "réponse à Q4",
    }
    fake_response = _make_function_call_response("finalize_interview", args)
    with patch.object(llm_client._client.aio.models, "generate_content", new=AsyncMock(return_value=fake_response)):
        result = await llm_client.send_turn([])

    assert result.is_finalize
    assert result.finalize == args


@pytest.mark.asyncio
async def test_send_turn_ignores_incomplete_finalize():
    args = {"answer_1": "x", "answer_2": "y"}  # manque answer_3 et answer_4
    fake_response = _make_function_call_response("finalize_interview", args)
    fake_response.text = "tentative incomplète"
    with patch.object(llm_client._client.aio.models, "generate_content", new=AsyncMock(return_value=fake_response)):
        result = await llm_client.send_turn([])

    # On retombe sur le texte si le tool n'a pas toutes les réponses.
    assert not result.is_finalize
    assert result.text == "tentative incomplète"
