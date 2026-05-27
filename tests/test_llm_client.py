from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from loeil import llm_client


def _make_text_response(text: str) -> SimpleNamespace:
    """Imite la forme d'une réponse Anthropic contenant uniquement du texte."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block])


def _make_tool_use_response(name: str, args: dict, extra_text: str | None = None) -> SimpleNamespace:
    """Imite la forme d'une réponse Anthropic avec un bloc tool_use."""
    blocks = []
    if extra_text:
        blocks.append(SimpleNamespace(type="text", text=extra_text))
    blocks.append(SimpleNamespace(type="tool_use", name=name, input=args, id="toolu_123"))
    return SimpleNamespace(content=blocks)


@pytest.mark.asyncio
async def test_send_turn_returns_text_when_no_tool_use():
    fake_response = _make_text_response("Question 1.")
    with patch.object(llm_client._client.messages, "create", new=AsyncMock(return_value=fake_response)):
        result = await llm_client.send_turn([{"role": "user", "content": "Bonjour"}])

    assert result.text == "Question 1."
    assert not result.is_finalize


@pytest.mark.asyncio
async def test_send_turn_returns_finalize_when_tool_use_complete():
    args = {
        "answer_1": "réponse à Q1",
        "answer_2": "réponse à Q2",
        "answer_3": "réponse à Q3",
        "answer_4": "réponse à Q4",
        "niveau": "PROFIL FORT",
        "score": 8,
        "tags": ["loyal", "compétent"],
        "synthese": "Profil solide, réponses précises.",
    }
    fake_response = _make_tool_use_response("finalize_interview", args)
    with patch.object(llm_client._client.messages, "create", new=AsyncMock(return_value=fake_response)):
        result = await llm_client.send_turn([])

    assert result.is_finalize
    assert result.finalize["answer_1"] == "réponse à Q1"
    assert result.finalize["niveau"] == "PROFIL FORT"
    assert result.finalize["score"] == 8
    assert result.finalize["tags"] == ["loyal", "compétent"]
    assert result.finalize["synthese"] == "Profil solide, réponses précises."


@pytest.mark.asyncio
async def test_send_turn_ignores_incomplete_tool_use():
    args = {"answer_1": "x", "answer_2": "y"}  # manque answer_3 et answer_4
    fake_response = _make_tool_use_response(
        "finalize_interview", args, extra_text="tentative incomplète"
    )
    with patch.object(llm_client._client.messages, "create", new=AsyncMock(return_value=fake_response)):
        result = await llm_client.send_turn([])

    # On retombe sur le texte si le tool n'a pas toutes les réponses.
    assert not result.is_finalize
    assert result.text == "tentative incomplète"


@pytest.mark.asyncio
async def test_send_turn_ignores_finalize_missing_verdict_fields():
    """finalize_interview avec les 4 réponses mais sans les champs verdict → retombe sur le texte."""
    args = {
        "answer_1": "réponse à Q1",
        "answer_2": "réponse à Q2",
        "answer_3": "réponse à Q3",
        "answer_4": "réponse à Q4",
        # niveau, score, tags, synthese absents
    }
    fake_response = _make_tool_use_response(
        "finalize_interview", args, extra_text="jugement en cours"
    )
    with patch.object(llm_client._client.messages, "create", new=AsyncMock(return_value=fake_response)):
        result = await llm_client.send_turn([])

    assert not result.is_finalize
    assert result.text == "jugement en cours"


@pytest.mark.asyncio
async def test_send_turn_accepts_finalize_with_score_zero_and_empty_tags():
    """score=0 et tags=[] sont des valeurs valides — ne doivent pas être rejetées."""
    args = {
        "answer_1": "réponse Q1",
        "answer_2": "réponse Q2",
        "answer_3": "réponse Q3",
        "answer_4": "réponse Q4",
        "niveau": "REJETÉ",
        "score": 0,
        "tags": [],
        "synthese": "Profil inadapté.",
    }
    fake_response = _make_tool_use_response("finalize_interview", args)
    with patch.object(llm_client._client.messages, "create", new=AsyncMock(return_value=fake_response)):
        result = await llm_client.send_turn([])

    assert result.is_finalize
    assert result.finalize["score"] == 0
    assert result.finalize["tags"] == []
