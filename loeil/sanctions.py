"""Avertissement puis mute : un manque de respect = avertissement, une récidive = mute."""
import logging
from datetime import timedelta

import discord

from loeil import config
from loeil.tension import Message

log = logging.getLogger("loeil.sanctions")

AVERTIR = "avertir"
MUTER = "muter"


class RegistreAvertissements:
    """Avertissements en mémoire. Un avertissement expire après `duree_secondes`."""

    def __init__(self, duree_secondes: float):
        self.duree_secondes = duree_secondes
        self._avertissements: dict[int, float] = {}

    def decision(self, membre_id: int, maintenant: float) -> str:
        """Retourne AVERTIR ou MUTER et met le registre à jour."""
        precedent = self._avertissements.get(membre_id)
        if precedent is not None and maintenant - precedent < self.duree_secondes:
            del self._avertissements[membre_id]  # on repart de zéro après le mute
            return MUTER
        self._avertissements[membre_id] = maintenant
        return AVERTIR


def ids_des_pseudos(pseudos: list[str], messages: list[Message]) -> list[int]:
    """Retrouve les auteurs (par leur id) à partir des pseudos renvoyés par l'IA."""
    cibles = {p.strip().lower() for p in pseudos if p.strip()}
    ids: list[int] = []
    for m in messages:
        if m.auteur.strip().lower() in cibles and m.auteur_id and m.auteur_id not in ids:
            ids.append(m.auteur_id)
    return ids


def est_protege(membre: discord.Member) -> bool:
    """Le staff et les chefs ne sont jamais sanctionnés par le bot."""
    if getattr(membre, "id", None) in config.MISSIONS_CHEF_IDS:
        return True
    perms = membre.guild_permissions
    return perms.administrator or perms.moderate_members or perms.manage_guild


async def appliquer(
    registre: RegistreAvertissements,
    salon: discord.TextChannel,
    membre_id: int,
    maintenant: float,
    raison: str,
) -> tuple[str, discord.Member] | None:
    """Avertit ou mute le membre. Retourne (action, membre) si quelque chose a été fait."""
    membre = salon.guild.get_member(membre_id)
    if membre is None:
        try:
            membre = await salon.guild.fetch_member(membre_id)
        except discord.HTTPException:
            log.warning("Membre %s introuvable, sanction ignorée", membre_id)
            return None
    if est_protege(membre):
        log.info("%s est staff : pas de sanction", membre.display_name)
        return None

    action = registre.decision(membre_id, maintenant)
    minutes = config.MUTE_MINUTES
    try:
        if action == AVERTIR:
            await salon.send(
                f"⚠️ {membre.mention}, avertissement. Le respect n'est pas négociable ici. "
                f"Au prochain écart, c'est {minutes} minutes de silence.",
                allowed_mentions=discord.AllowedMentions(users=[membre]),
            )
        else:
            await membre.timeout(timedelta(minutes=minutes), reason=f"L'Œil — récidive : {raison}"[:500])
            await salon.send(
                f"🔇 {membre.mention} a été averti et a recommencé. {minutes} minutes de silence.",
                allowed_mentions=discord.AllowedMentions(users=[membre]),
            )
    except discord.Forbidden:
        log.error("Pas la permission de %s %s (rôle de L'Œil trop bas ou permission manquante)",
                  action, membre.display_name)
        return None
    except discord.HTTPException as exc:
        log.error("Échec de l'action %s sur %s : %s", action, membre.display_name, exc)
        return None
    log.info("%s : %s (%s)", action, membre.display_name, raison)
    return action, membre
