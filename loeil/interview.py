import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import discord

from loeil import llm_client, prompts, staff_channel

log = logging.getLogger("loeil.interview")


@dataclass
class Interview:
    candidate: discord.abc.User
    started_at: datetime = field(default_factory=datetime.now)
    history: list[dict] = field(default_factory=list)
    in_flight: bool = False


_active: dict[int, Interview] = {}


def is_active(user_id: int) -> bool:
    return user_id in _active


async def start(
    bot: discord.Client,
    user: discord.abc.User,
    guild: Optional[discord.Guild] = None,
) -> None:
    """Démarre un entretien : envoie le message d'ouverture en DM, enregistre l'état."""
    if user.id in _active:
        try:
            await user.send(prompts.ALREADY_ACTIVE)
        except (discord.Forbidden, discord.HTTPException):
            pass
        return

    try:
        await user.send(prompts.OPENING_MESSAGE)
    except discord.Forbidden:
        log.info("DMs fermés pour %s (%s)", user, user.id)
        await _notify_dms_closed(guild, user)
        return
    except discord.HTTPException as exc:
        log.warning("Échec d'envoi du message d'ouverture à %s : %s", user.id, exc)
        return

    interview = Interview(candidate=user)
    interview.history.append({"role": "model", "parts": [{"text": prompts.OPENING_MESSAGE}]})
    _active[user.id] = interview
    log.info("Entretien démarré avec %s (%s)", user, user.id)


async def _notify_dms_closed(guild: Optional[discord.Guild], user: discord.abc.User) -> None:
    if guild is None or guild.system_channel is None:
        return
    try:
        await guild.system_channel.send(prompts.DM_CLOSED_PUBLIC.format(mention=user.mention))
    except discord.HTTPException as exc:
        log.warning("Impossible de poster dans le channel système : %s", exc)


async def handle_response(bot: discord.Client, user: discord.abc.User, content: str) -> None:
    """Appelée pour chaque DM reçu d'un candidat. Ignore si pas d'entretien actif."""
    interview = _active.get(user.id)
    if interview is None:
        return
    if interview.in_flight:
        # Évite les appels concurrents si l'utilisateur spam plusieurs messages.
        return

    interview.in_flight = True
    interview.history.append({"role": "user", "parts": [{"text": content}]})

    try:
        try:
            response = await llm_client.send_turn(interview.history)
        except Exception:
            log.exception("Erreur LLM pour user_id=%s", user.id)
            interview.history.pop()
            try:
                await user.send("Système instable. Reprends.")
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        if response.is_finalize:
            await _complete_interview(bot, user, interview, response.finalize or {})
            return

        if not response.text:
            log.warning("Réponse vide de Gemini pour user_id=%s", user.id)
            interview.history.pop()
            return

        interview.history.append({"role": "model", "parts": [{"text": response.text}]})
        try:
            await user.send(response.text)
        except discord.Forbidden:
            log.warning("DMs fermés pendant l'entretien pour user_id=%s", user.id)
            _active.pop(user.id, None)
        except discord.HTTPException as exc:
            log.warning("Échec d'envoi de la réponse à %s : %s", user.id, exc)
    finally:
        if user.id in _active:
            _active[user.id].in_flight = False


async def _complete_interview(
    bot: discord.Client,
    user: discord.abc.User,
    interview: Interview,
    answers: dict[str, str],
) -> None:
    try:
        await staff_channel.post_application(bot, interview.candidate, interview.started_at, answers)
    except Exception:
        log.exception("Échec de l'envoi du résumé au channel staff pour user_id=%s", user.id)

    try:
        await user.send(prompts.CLOSING_MESSAGE)
    except (discord.Forbidden, discord.HTTPException):
        pass

    _active.pop(user.id, None)
    log.info("Entretien terminé avec %s (%s)", user, user.id)
