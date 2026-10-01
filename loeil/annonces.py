"""Mémoire d'un salon d'infos (annonces, bilans de réunion) : L'Œil s'en sert pour répondre."""
import logging
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord

log = logging.getLogger("loeil.annonces")

NB_ANNONCES = 30
MAX_CARACTERES_ANNONCE = 1500
FUSION_MAX = timedelta(minutes=15)
FUSEAU = ZoneInfo("Europe/Paris")


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
        self._dernier_ajout: datetime | None = None

    def ajouter(self, date: datetime, auteur: str, contenu: str) -> None:
        if not contenu:
            return
        precedente = self.annonces[-1] if self.annonces else None
        # Un long texte posté en plusieurs messages d'affilée par la même personne = une seule entrée.
        if (precedente is not None and precedente.auteur == auteur and self._dernier_ajout is not None
                and timedelta(0) <= date - self._dernier_ajout <= FUSION_MAX):
            precedente.contenu = (precedente.contenu + "\n" + contenu)[:self.max_caracteres]
        else:
            self.annonces.append(Annonce(date, auteur, contenu[:self.max_caracteres]))
        self._dernier_ajout = date

    def ajouter_message(self, message: discord.Message) -> None:
        self.ajouter(message.created_at, message.author.display_name, contenu_message(message))

    async def charger(self, salon: discord.abc.Messageable) -> None:
        self.annonces.clear()
        self._dernier_ajout = None
        # Plus de messages que d'entrées : certains seront fusionnés.
        messages = [m async for m in salon.history(limit=self.annonces.maxlen * 4)]
        for message in reversed(messages):  # du plus ancien au plus récent
            self.ajouter_message(message)
        log.info("%d entrée(s) chargée(s) depuis #%s", len(self.annonces), getattr(salon, "name", "?"))

    def texte(self) -> str:
        """Du plus récent (n°1) au plus ancien, avec date et heure de publication (heure de Paris)."""
        if not self.annonces:
            return "(rien de connu)"
        blocs = []
        for rang, a in enumerate(reversed(self.annonces), start=1):
            date = a.date.astimezone(FUSEAU) if a.date.tzinfo else a.date
            marque = " — LE PLUS RÉCENT" if rang == 1 else ""
            blocs.append(f"[n°{rang}{marque} — publié le {date:%d/%m/%Y à %Hh%M} par {a.auteur}]\n{a.contenu}")
        return "\n\n".join(blocs)
