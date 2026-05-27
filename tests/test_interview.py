from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from loeil import interview, prompts


def _make_user(user_id: int = 42, name: str = "Candidat#0001") -> MagicMock:
    user = MagicMock(spec=discord.abc.User)
    user.id = user_id
    user.mention = f"<@{user_id}>"
    user.__str__ = MagicMock(return_value=name)
    user.send = AsyncMock()
    return user


def _make_guild_with_system_channel() -> MagicMock:
    system = MagicMock()
    system.send = AsyncMock()
    guild = MagicMock(spec=discord.Guild)
    guild.system_channel = system
    return guild


@pytest.fixture(autouse=True)
def clear_active_interviews():
    interview._active.clear()
    yield
    interview._active.clear()


@pytest.mark.asyncio
async def test_start_sends_opening_and_registers_active_interview():
    user = _make_user()
    bot = MagicMock()

    await interview.start(bot, user)

    user.send.assert_awaited_once_with(prompts.OPENING_MESSAGE)
    assert interview.is_active(user.id)


@pytest.mark.asyncio
async def test_start_refuses_when_already_active():
    user = _make_user()
    bot = MagicMock()
    await interview.start(bot, user)
    user.send.reset_mock()

    await interview.start(bot, user)

    user.send.assert_awaited_once_with(prompts.ALREADY_ACTIVE)


@pytest.mark.asyncio
async def test_start_falls_back_to_system_channel_when_dms_closed():
    user = _make_user()
    user.send.side_effect = discord.Forbidden(MagicMock(status=403), "DMs closed")
    bot = MagicMock()
    guild = _make_guild_with_system_channel()

    await interview.start(bot, user, guild)

    assert not interview.is_active(user.id)
    guild.system_channel.send.assert_awaited_once()
    sent = guild.system_channel.send.await_args.args[0]
    assert user.mention in sent
    assert "messages privés" in sent


@pytest.mark.asyncio
async def test_handle_response_ignored_when_no_active_interview():
    user = _make_user()
    bot = MagicMock()

    with patch("loeil.interview.llm_client.send_turn", new=AsyncMock()) as mock_llm:
        await interview.handle_response(bot, user, "salut")

    mock_llm.assert_not_called()
    user.send.assert_not_called()


@pytest.mark.asyncio
async def test_handle_response_relays_llm_text_to_candidate():
    user = _make_user()
    bot = MagicMock()
    await interview.start(bot, user)
    user.send.reset_mock()

    fake_response = SimpleNamespace(text="Question 1.", finalize=None, is_finalize=False)
    with patch("loeil.interview.llm_client.send_turn", new=AsyncMock(return_value=fake_response)):
        await interview.handle_response(bot, user, "ok")

    user.send.assert_awaited_once_with("Question 1.")


@pytest.mark.asyncio
async def test_handle_response_finalize_posts_to_staff_and_clears_active():
    user = _make_user()
    bot = MagicMock()
    await interview.start(bot, user)
    user.send.reset_mock()

    answers = {f"answer_{i}": f"r{i}" for i in range(1, 5)}
    fake_response = SimpleNamespace(text=None, finalize=answers, is_finalize=True)

    with patch("loeil.interview.llm_client.send_turn", new=AsyncMock(return_value=fake_response)), \
         patch("loeil.interview.staff_channel.post_application", new=AsyncMock()) as mock_post:
        await interview.handle_response(bot, user, "dernière réponse")

    mock_post.assert_awaited_once()
    args, _ = mock_post.await_args
    assert args[1] is user
    assert args[3] == answers
    user.send.assert_awaited_with(prompts.CLOSING_MESSAGE)
    assert not interview.is_active(user.id)


@pytest.mark.asyncio
async def test_handle_response_recovers_from_llm_error():
    user = _make_user()
    bot = MagicMock()
    await interview.start(bot, user)
    user.send.reset_mock()
    initial_history_len = len(interview._active[user.id].history)

    with patch("loeil.interview.llm_client.send_turn", new=AsyncMock(side_effect=RuntimeError("API down"))):
        await interview.handle_response(bot, user, "première réponse")

    # Le message utilisateur a été retiré de l'historique pour permettre un retry propre.
    assert len(interview._active[user.id].history) == initial_history_len
    user.send.assert_awaited_with("Système instable. Reprends.")
    # L'entretien reste actif pour permettre la suite.
    assert interview.is_active(user.id)
