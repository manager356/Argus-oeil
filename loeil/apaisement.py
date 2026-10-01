"""Surveillance des salons HRP : analyse IA quand ça chauffe, message d'apaisement, alerte staff."""
import asyncio
import logging
import time

import discord

from loeil import config
from loeil import sanctions
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
_registre = sanctions.RegistreAvertissements(config.AVERTISSEMENT_HEURES * 3600)


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
    contenu = message.content
    reference = message.reference.resolved if message.reference else None
    if bot.user and (bot.user in message.mentions or
                     (isinstance(reference, discord.Message) and reference.author.id == bot.user.id)):
        contenu = f"[adressé à L'Œil] {contenu}"
    etat.ajouter(Message(message.author.display_name, contenu, message.jump_url, message.author.id), suspect)

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
    if not etat.doit_analyser():
        return
    historique = list(etat.historique)
    nouveaux = etat.nouveaux()
    etat.marquer_analyse()
    verdict = await _get_analyseur().analyser(historique, len(nouveaux))
    if verdict is None:
        return
    log.info("Salon %s : tension niveau %s (%s) irrespectueux=%s",
             salon.id, verdict.niveau, verdict.raison, verdict.irrespectueux)

    maintenant = time.monotonic()
    actions = []
    if config.SANCTIONS_ENABLED:
        for membre_id in sanctions.ids_des_pseudos(verdict.irrespectueux, nouveaux):
            resultat = await sanctions.appliquer(_registre, salon, membre_id, maintenant, verdict.raison)
            if resultat:
                actions.append(resultat)

    # Pas plus d'un message d'apaisement toutes les 30 min par salon.
    if verdict.niveau >= 2 and verdict.message_apaisement and not etat.en_pause(maintenant, PAUSE_APRES_INTERVENTION_SECONDES):
        etat.marquer_intervention(maintenant)
        try:
            await salon.send(verdict.message_apaisement, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            log.error("Impossible de poster l'apaisement dans %s : %s", salon.id, exc)

    mutes = [membre for action, membre in actions if action == sanctions.MUTER]
    if verdict.niveau >= 3 or mutes:
        await _alerter_staff(bot, salon, verdict, historique[-1].lien, mutes)


async def _alerter_staff(bot: discord.Client, salon: discord.abc.GuildChannel, verdict: Verdict, lien: str,
                         mutes: list[discord.Member]) -> None:
    salon_staff = bot.get_channel(config.TENSION_STAFF_CHANNEL_ID or 0)
    if salon_staff is None:
        log.warning("Alerte niveau 3 non envoyée : salon staff %s introuvable", config.TENSION_STAFF_CHANNEL_ID)
        return
    embed = discord.Embed(
        title=f"⚠️ Tension dans #{salon.name}" if verdict.niveau < 3 else f"⚠️ Grosse tension dans #{salon.name}",
        description=verdict.raison,
        color=discord.Color.red(),
    )
    if verdict.personnes:
        embed.add_field(name="Personnes impliquées", value=", ".join(verdict.personnes)[:1024], inline=False)
    if mutes:
        embed.add_field(name=f"🔇 Mute {config.MUTE_MINUTES} min (récidive)",
                        value=", ".join(m.mention for m in mutes)[:1024], inline=False)
    embed.add_field(name="Conversation", value=f"[Aller voir]({lien})", inline=False)
    embed.set_footer(text="Pour lever un mute : clic droit sur le membre → Retirer l'exclusion temporaire.")
    role = config.TENSION_STAFF_ROLE_ID
    try:
        await salon_staff.send(
            content=f"<@&{role}>" if role else None,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
    except discord.HTTPException as exc:
        log.error("Impossible de poster l'alerte staff : %s", exc)
