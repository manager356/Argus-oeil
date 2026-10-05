"""Réglages modifiables depuis Discord, gardés dans un message « ⚙️ Réglages de L'Œil » (survit aux redémarrages)."""
import logging
import re

import discord

log = logging.getLogger("loeil.reglages")

MARQUE = "reglages-oeil"
LIBELLES = {"heure_sondage": "Heure du sondage de présence"}


def heure_valide(texte: str) -> str | None:
    """« 18h », « 18:30 », « 9h05 » -> « HH:MM », sinon None."""
    m = re.fullmatch(r"\s*(\d{1,2})\s*[h:]\s*(\d{2})?\s*", texte.lower())
    if not m:
        return None
    heures, minutes = int(m.group(1)), int(m.group(2) or 0)
    if heures > 23 or minutes > 59:
        return None
    return f"{heures:02d}:{minutes:02d}"


def embed_reglages(valeurs: dict[str, str]) -> discord.Embed:
    embed = discord.Embed(title="⚙️ Réglages de L'Œil", color=discord.Color.dark_grey(),
                          description="Modifiés par commande. Ne supprime pas ce message.")
    for cle, valeur in valeurs.items():
        embed.add_field(name=LIBELLES.get(cle, cle), value=f"`{cle}` = {valeur}", inline=False)
    embed.set_footer(text=MARQUE)
    return embed


def lire_reglages(embed: discord.Embed) -> dict[str, str]:
    valeurs = {}
    for champ in embed.fields:
        m = re.fullmatch(r"`([a-z_]+)` = (.+)", champ.value or "", re.S)
        if m:
            valeurs[m.group(1)] = m.group(2).strip()
    return valeurs


class Reglages:
    def __init__(self) -> None:
        self.valeurs: dict[str, str] = {}
        self._message: discord.Message | None = None

    async def charger(self, salon: discord.abc.Messageable, bot_id: int) -> None:
        async for message in salon.history(limit=200):
            if message.author.id == bot_id and message.embeds and message.embeds[0].footer.text == MARQUE:
                self._message = message
                self.valeurs = lire_reglages(message.embeds[0])
                log.info("Réglages relus : %s", self.valeurs)
                return

    async def definir(self, salon: discord.abc.Messageable, cle: str, valeur: str) -> None:
        self.valeurs[cle] = valeur
        embed = embed_reglages(self.valeurs)
        if self._message is None:
            self._message = await salon.send(embed=embed)
        else:
            await self._message.edit(embed=embed)
