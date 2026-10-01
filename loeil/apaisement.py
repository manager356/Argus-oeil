"""Surveillance des salons HRP : analyse IA quand ça chauffe, message d'apaisement, alerte staff."""
import asyncio
import logging
import time

import discord

from loeil import config
from loeil.analyseur import Analyseur, Verdict
from loeil.tension import MOTS_DECLENCHEURS, EtatSalon, Message, compiler_declencheurs, est_suspect

log = logging.getLogger("loeil.apaisement")

NB_MESSAGES_CONTEXTE = 20
ATTENTE_AVANT_ANALYSE_SECONDES = 45
PAUSE_APRES_INTERVENTION_SECONDES = 30 * 60

_declencheurs = compiler_declencheurs(MOTS_DECLENCHEURS)
_etats: dict[int, EtatSalon] = {}
_analyses_prevues: dict[int, asyncio.Task] = {}
_analyseur: Analyseur | None = None


def _get_analyseur() -> Analyseur:
    global _analyseur
    if _analyseur is None:
        _analyseur = Analyseur(config.TENSION_MODEL)
    return _analyseur


async def on_guild_message(bot: discord.Client, message: discord.Message) -> None:
    """À appeler pour chaque message de serveur (hors bots)."""
    salon_id = message.channel.id
    if salon_id not in config.TENSION_CHANNEL_IDS or not message.content.strip():
        return
    etat = _etats.setdefault(salon_id, EtatSalon(NB_MESSAGES_CONTEXTE))
    suspect = est_suspect(message.content, _declencheurs)
    etat.ajouter(Message(message.author.display_name, message.content, message.jump_url), suspect)

    # On attend que la conversation se pose : chaque nouveau message repousse l'analyse.
    if etat.suspect:
        prevue = _analyses_prevues.get(salon_id)
        if prevue and not prevue.done():
            prevue.cancel()
        _analyses_prevues[salon_id] = asyncio.create_task(_analyser_plus_tard(bot, message.channel))


async def _analyser_plus_tard(bot: discord.Client, salon: discord.abc.GuildChannel) -> None:
    try:
        await asyncio.sleep(ATTENTE_AVANT_ANALYSE_SECONDES)
    except asyncio.CancelledError:
        return
    etat = _etats[salon.id]
    if not etat.doit_analyser(time.monotonic(), PAUSE_APRES_INTERVENTION_SECONDES):
        etat.marquer_analyse()
        return
    etat.marquer_analyse()
    historique = list(etat.historique)
    verdict = await _get_analyseur().analyser(historique)
    if verdict is None:
        return
    log.info("Salon %s : tension niveau %s (%s)", salon.id, verdict.niveau, verdict.raison)
    if verdict.niveau < 2 or not verdict.message_apaisement:
        return
    etat.marquer_intervention(time.monotonic())
    try:
        await salon.send(verdict.message_apaisement, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException as exc:
        log.error("Impossible de poster l'apaisement dans %s : %s", salon.id, exc)
    if verdict.niveau >= 3:
        await _alerter_staff(bot, salon, verdict, historique[-1].lien)


async def _alerter_staff(bot: discord.Client, salon: discord.abc.GuildChannel, verdict: Verdict, lien: str) -> None:
    salon_staff = bot.get_channel(config.TENSION_STAFF_CHANNEL_ID)
    if salon_staff is None:
        log.warning("Alerte niveau 3 non envoyée : salon staff %s introuvable", config.TENSION_STAFF_CHANNEL_ID)
        return
    embed = discord.Embed(
        title=f"⚠️ Grosse tension dans #{salon.name}",
        description=verdict.raison,
        color=discord.Color.red(),
    )
    if verdict.personnes:
        embed.add_field(name="Personnes impliquées", value=", ".join(verdict.personnes)[:1024], inline=False)
    embed.add_field(name="Conversation", value=f"[Aller voir]({lien})", inline=False)
    embed.set_footer(text="L'Œil a posté un message d'apaisement. À vous de juger la suite.")
    role = config.TENSION_STAFF_ROLE_ID
    try:
        await salon_staff.send(
            content=f"<@&{role}>" if role else None,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
    except discord.HTTPException as exc:
        log.error("Impossible de poster l'alerte staff : %s", exc)
