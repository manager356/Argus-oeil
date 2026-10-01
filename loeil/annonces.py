"""Mémoire d'un salon d'infos (annonces, bilans de réunion) : L'Œil s'en sert pour répondre."""
import logging
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import discord

log = logging.getLogger("loeil.annonces")

NB_ANNONCES = 30
MAX_CARACTERES_ANNONCE = 1500


@dataclass
class Annonce:
    date: datetime
    auteur: str
    contenu: str


def remplacer_mentions(texte: str, guild: discord.Guild | None) -> str:
    """<@123> -> @Pseudo, pour que l'IA sache de qui on parle."""
    def nom(m: re.Match) -> str:
        membre = guild.get_member(int(m.group(1))) if guild else None
        return f"@{membre.display_name}" if membre else m.group(0)
    return re.sub(r"<@!?(\d+)>", nom, texte)


def contenu_message(message: discord.Message) -> str:
    """Texte du message + texte des embeds (beaucoup d'annonces sont en embed)."""
    morceaux = [message.content] if message.content else []
    for embed in message.embeds:
        morceaux += [t for t in (embed.title, embed.description) if t]
        morceaux += [f"{champ.name} : {champ.value}" for champ in embed.fields]
    return remplacer_mentions("\n".join(morceaux).strip(), message.guild)


class MemoireAnnonces:
    def __init__(self, taille: int = NB_ANNONCES, max_caracteres: int = MAX_CARACTERES_ANNONCE):
        self.annonces: deque[Annonce] = deque(maxlen=taille)
        self.max_caracteres = max_caracteres

    def ajouter(self, date: datetime, auteur: str, contenu: str) -> None:
        if contenu:
            self.annonces.append(Annonce(date, auteur, contenu[:self.max_caracteres]))

    def ajouter_message(self, message: discord.Message) -> None:
        self.ajouter(message.created_at, message.author.display_name, contenu_message(message))

    async def charger(self, salon: discord.abc.Messageable) -> None:
        self.annonces.clear()
        messages = [m async for m in salon.history(limit=self.annonces.maxlen)]
        for message in reversed(messages):  # du plus ancien au plus récent
            self.ajouter_message(message)
        log.info("%d annonce(s) chargée(s)", len(self.annonces))

    def texte(self) -> str:
        if not self.annonces:
            return "(rien de connu)"
        return "\n\n".join(
            f"[{a.date:%d/%m/%Y} — {a.auteur}]\n{a.contenu}" for a in self.annonces
        )
