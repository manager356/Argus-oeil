from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from loeil import prompts, staff_channel


def _make_candidate(name: str = "Nick#0001", mention: str = "<@123>") -> SimpleNamespace:
    return SimpleNamespace(__str__=lambda self=None: name, mention=mention, id=123)


def test_build_embed_contains_all_four_questions():
    candidate = _make_candidate()
    answers = {
        "answer_1": "Je suis parti car ils étaient faibles.",
        "answer_2": "Je demande des précisions avant d'exécuter.",
        "answer_3": "Réseau, contacts au port, conduite défensive.",
        "answer_4": "Que vous me laissiez régler ça moi-même.",
    }
    started = datetime(2025, 5, 27, 14, 30)

    embed = staff_channel.build_embed(candidate, started, answers)

    assert embed.title == "Nouvelle candidature"
    assert "2025-05-27 14:30" in embed.description
    assert len(embed.fields) == 4
    for index, field in enumerate(embed.fields, start=1):
        assert field.name.startswith(f"Q{index}.")
        assert field.value == answers[f"answer_{index}"]


def test_build_embed_uses_placeholder_for_missing_answer():
    candidate = _make_candidate()
    answers = {"answer_1": "x", "answer_2": "y", "answer_3": "z"}  # answer_4 missing
    started = datetime(2025, 5, 27, 14, 30)

    embed = staff_channel.build_embed(candidate, started, answers)

    assert embed.fields[3].value == "—"


def test_build_embed_truncates_long_answers():
    candidate = _make_candidate()
    long_answer = "a" * 2000
    answers = {f"answer_{i}": long_answer for i in range(1, 5)}
    started = datetime(2025, 5, 27, 14, 30)

    embed = staff_channel.build_embed(candidate, started, answers)

    for field in embed.fields:
        assert len(field.value) <= 1024
        assert field.value.endswith("…")


@pytest.mark.asyncio
async def test_post_application_sends_embed_to_staff_channel():
    candidate = _make_candidate()
    started = datetime(2025, 5, 27, 14, 30)
    answers = {f"answer_{i}": f"réponse {i}" for i in range(1, 5)}

    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_bot = MagicMock()
    mock_bot.get_channel.return_value = mock_channel

    await staff_channel.post_application(mock_bot, candidate, started, answers)

    mock_bot.get_channel.assert_called_once()
    mock_channel.send.assert_awaited_once()
    sent_embed = mock_channel.send.await_args.kwargs["embed"]
    assert sent_embed.title == "Nouvelle candidature"
    assert len(sent_embed.fields) == len(prompts.QUESTIONS)
