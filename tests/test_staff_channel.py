from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from loeil import prompts, staff_channel


def _make_candidate(name: str = "Nick#0001", mention: str = "<@123>") -> SimpleNamespace:
    return SimpleNamespace(__str__=lambda self=None: name, mention=mention, id=123)


def _answers_complets(
    niveau: str = "PROFIL FORT",
    score: int = 7,
    tags: list[str] | None = None,
    synthese: str = "Profil intéressant.",
) -> dict:
    return {
        "answer_1": "Je suis parti car ils étaient faibles.",
        "answer_2": "Je demande des précisions avant d'exécuter.",
        "answer_3": "Réseau, contacts au port, conduite défensive.",
        "answer_4": "Que vous me laissiez régler ça moi-même.",
        "niveau": niveau,
        "score": score,
        "tags": tags if tags is not None else [],
        "synthese": synthese,
    }


# --- Tests existants mis à jour ---

def test_build_embed_contains_all_four_questions():
    candidate = _make_candidate()
    answers = _answers_complets()
    started = datetime(2025, 5, 27, 14, 30)

    embed = staff_channel.build_embed(candidate, started, answers)

    assert embed.title == "Nouvelle candidature — PROFIL FORT"
    assert "2025-05-27 14:30" in embed.description
    # 1 champ verdict + 4 champs questions = 5
    assert len(embed.fields) == 5
    assert embed.fields[0].name == "Verdict de L'Œil"
    for index, field in enumerate(embed.fields[1:], start=1):
        assert field.name.startswith(f"Q{index}.")
        assert field.value == answers[f"answer_{index}"]


def test_build_embed_uses_placeholder_for_missing_answer():
    candidate = _make_candidate()
    # Pas de champs verdict, pas de answer_4
    answers = {"answer_1": "x", "answer_2": "y", "answer_3": "z"}
    started = datetime(2025, 5, 27, 14, 30)

    embed = staff_channel.build_embed(candidate, started, answers)

    # Q4 est maintenant à l'index 4 (après le champ verdict en index 0)
    assert embed.fields[4].value == "—"


def test_build_embed_truncates_long_answers():
    candidate = _make_candidate()
    long_answer = "a" * 2000
    answers = {f"answer_{i}": long_answer for i in range(1, 5)}
    answers.update({
        "niveau": "REJETÉ",
        "score": 2,
        "tags": [],
        "synthese": long_answer,
    })
    started = datetime(2025, 5, 27, 14, 30)

    embed = staff_channel.build_embed(candidate, started, answers)

    # Tous les 5 champs (verdict + Q1-Q4) doivent être tronqués
    for field in embed.fields:
        assert len(field.value) <= 1024
        assert field.value.endswith("…")


@pytest.mark.asyncio
async def test_post_application_sends_embed_to_staff_channel():
    candidate = _make_candidate()
    started = datetime(2025, 5, 27, 14, 30)
    answers = _answers_complets(niveau="PROFIL FORT", score=7, tags=["loyal"], synthese="Bon profil.")

    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_bot = MagicMock()
    mock_bot.get_channel.return_value = mock_channel

    await staff_channel.post_application(mock_bot, candidate, started, answers)

    mock_bot.get_channel.assert_called_once()
    mock_channel.send.assert_awaited_once()
    sent_embed = mock_channel.send.await_args.kwargs["embed"]
    assert sent_embed.title == "Nouvelle candidature — PROFIL FORT"
    # verdict field + Q1-Q4
    assert len(sent_embed.fields) == len(prompts.QUESTIONS) + 1


# --- Nouveaux tests ---

def test_build_embed_color_profil_fort():
    candidate = _make_candidate()
    embed = staff_channel.build_embed(candidate, datetime(2025, 5, 27, 14, 30), _answers_complets(niveau="PROFIL FORT"))
    assert embed.color.value == 0x22C55E


def test_build_embed_color_a_surveiller():
    candidate = _make_candidate()
    embed = staff_channel.build_embed(candidate, datetime(2025, 5, 27, 14, 30), _answers_complets(niveau="À SURVEILLER", score=4))
    assert embed.color.value == 0xF59E0B


def test_build_embed_color_rejete():
    candidate = _make_candidate()
    embed = staff_channel.build_embed(candidate, datetime(2025, 5, 27, 14, 30), _answers_complets(niveau="REJETÉ", score=1))
    assert embed.color.value == 0xEF4444


def test_build_embed_score_and_tags_in_description():
    candidate = _make_candidate()
    answers = _answers_complets(score=8, tags=["loyal", "discret"])
    embed = staff_channel.build_embed(candidate, datetime(2025, 5, 27, 14, 30), answers)

    assert "Score : 8/10" in embed.description
    assert "[loyal]" in embed.description
    assert "[discret]" in embed.description


def test_build_embed_verdict_field_with_synthese():
    candidate = _make_candidate()
    synthese = "Candidat solide. Réponses précises. Potentiel confirmé."
    answers = _answers_complets(synthese=synthese)
    embed = staff_channel.build_embed(candidate, datetime(2025, 5, 27, 14, 30), answers)

    assert embed.fields[0].name == "Verdict de L'Œil"
    assert embed.fields[0].value == synthese
