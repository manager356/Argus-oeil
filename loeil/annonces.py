"""Mémoire des annonces du serveur : L'Œil s'en sert pour répondre aux questions."""
import logging
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


def contenu_message(message: discord.Message) -> str:
    """Texte du message + texte des embeds (beaucoup d'annonces sont en embed)."""
    morceaux = [message.content] if message.content else []
    for embed in message.embeds:
        morceaux += [t for t in (embed.title, embed.description) if t]
        morceaux += [f"{champ.name} : {champ.value}" for champ in embed.fields]
    return "\n".join(morceaux).strip()


class MemoireAnnonces:
    def __init__(self, taille: int = NB_ANNONCES):
        self.annonces: deque[Annonce] = deque(maxlen=taille)

    def ajouter(self, date: datetime, auteur: str, contenu: str) -> None:
        if contenu:
            self.annonces.append(Annonce(date, auteur, contenu[:MAX_CARACTERES_ANNONCE]))

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
            return "(aucune annonce connue)"
        return "\n\n".join(
            f"[{a.date:%d/%m/%Y} — {a.auteur}]\n{a.contenu}" for a in self.annonces
        )
