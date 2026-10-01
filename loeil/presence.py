"""Sondage de présence quotidien : boutons Présent / Absent / Peut-être."""
import json
import logging
import re
from datetime import date
from pathlib import Path

import discord

log = logging.getLogger("loeil.presence")

CHOIX = {
    "present": ("✅", "Présents", discord.ButtonStyle.success, "Présent"),
    "absent": ("❌", "Absents", discord.ButtonStyle.danger, "Absent"),
    "peutetre": ("⏳", "Peut-être / en retard", discord.ButtonStyle.secondary, "Peut-être"),
}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
MAX_SONDAGES_GARDES = 14
MAX_CARACTERES_CHAMP = 1024


def titre_du_jour(jour: date) -> str:
    return f"📋 Présence du {JOURS[jour.weekday()]} {jour.day} {MOIS[jour.month - 1]}"


def votes_vides() -> dict[str, list[int]]:
    return {cle: [] for cle in CHOIX}


def appliquer_vote(votes: dict[str, list[int]], membre_id: int, choix: str) -> dict[str, list[int]]:
    """Place le membre dans `choix`. Recliquer sur le même bouton retire son vote."""
    deja_la = membre_id in votes[choix]
    nouveaux = {cle: [m for m in ids if m != membre_id] for cle, ids in votes.items()}
    if not deja_la:
        nouveaux[choix].append(membre_id)
    return nouveaux


def texte_champ(ids: list[int]) -> str:
    if not ids:
        return "—"
    texte = ""
    for i, membre_id in enumerate(ids):
        morceau = f"<@{membre_id}>\n"
        reste = len(ids) - i
        if len(texte) + len(morceau) > MAX_CARACTERES_CHAMP - 20:
            return texte + f"… et {reste} autre(s)"
        texte += morceau
    return texte.rstrip("\n")


def construire_embed(titre: str, votes: dict[str, list[int]]) -> discord.Embed:
    embed = discord.Embed(
        title=titre,
        description="Qui sera là ce soir ? Clique sur un bouton (reclique pour retirer ton vote).",
        color=discord.Color.blurple(),
    )
    for cle, (emoji, libelle, _, _) in CHOIX.items():
        ids = votes[cle]
        embed.add_field(name=f"{emoji} {libelle} ({len(ids)})", value=texte_champ(ids), inline=True)
    return embed


def lire_votes_embed(embed: discord.Embed) -> dict[str, list[int]]:
    """Retrouve les votes à partir des mentions affichées dans l'embed (un champ par choix)."""
    votes = votes_vides()
    for cle, champ in zip(CHOIX, embed.fields):
        votes[cle] = [int(i) for i in re.findall(r"<@!?(\d+)>", champ.value or "")]
    return votes


class StockageVotes:
    """Votes enregistrés dans un fichier JSON pour survivre aux redémarrages du bot."""

    def __init__(self, chemin: Path):
        self.chemin = chemin
        self.donnees: dict[str, dict] = {}
        if chemin.exists():
            try:
                self.donnees = json.loads(chemin.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.error("Fichier %s illisible, on repart de zéro", chemin)

    def creer(self, message_id: int, titre: str) -> None:
        self.restaurer(message_id, titre, votes_vides())

    def restaurer(self, message_id: int, titre: str, votes: dict[str, list[int]]) -> dict:
        self.donnees[str(message_id)] = {"titre": titre, "votes": votes}
        # On ne garde que les sondages récents.
        for ancien in list(self.donnees)[:-MAX_SONDAGES_GARDES]:
            del self.donnees[ancien]
        self.sauver()
        return self.donnees[str(message_id)]

    def obtenir(self, message_id: int) -> dict | None:
        return self.donnees.get(str(message_id))

    def sauver(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.chemin.write_text(json.dumps(self.donnees, ensure_ascii=False, indent=1), encoding="utf-8")


class BoutonPresence(discord.ui.Button):
    def __init__(self, cle: str, stockage: StockageVotes):
        emoji, _, style, libelle = CHOIX[cle]
        super().__init__(label=libelle, emoji=emoji, style=style, custom_id=f"presence:{cle}")
        self.cle = cle
        self.stockage = stockage

    async def callback(self, interaction: discord.Interaction) -> None:
        sondage = self.stockage.obtenir(interaction.message.id)
        if sondage is None:
            # Fichier perdu (ex. redéploiement Railway) : on relit les votes affichés.
            if not interaction.message.embeds:
                await interaction.response.send_message("Sondage illisible, vote sur celui du jour 🙂", ephemeral=True)
                return
            embed = interaction.message.embeds[0]
            sondage = self.stockage.restaurer(interaction.message.id, embed.title or "", lire_votes_embed(embed))
        sondage["votes"] = appliquer_vote(sondage["votes"], interaction.user.id, self.cle)
        self.stockage.sauver()
        await interaction.response.edit_message(embed=construire_embed(sondage["titre"], sondage["votes"]))


class VuePresence(discord.ui.View):
    """Vue persistante : les boutons marchent encore après un redémarrage du bot."""

    def __init__(self, stockage: StockageVotes):
        super().__init__(timeout=None)
        for cle in CHOIX:
            self.add_item(BoutonPresence(cle, stockage))


async def publier_sondage(salon: discord.abc.Messageable, stockage: StockageVotes,
                          jour: date, role_id: int = 0) -> discord.Message:
    titre = titre_du_jour(jour)
    contenu = f"<@&{role_id}>" if role_id else None
    message = await salon.send(
        content=contenu,
        embed=construire_embed(titre, votes_vides()),
        view=VuePresence(stockage),
        allowed_mentions=discord.AllowedMentions(roles=True),
    )
    stockage.creer(message.id, titre)
    return message
