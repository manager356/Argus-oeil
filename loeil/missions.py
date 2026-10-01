"""Missions du soir : liste des présents aux chefs, missions envoyées en MP, suivi et rapport."""
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

import discord

from loeil import config
from loeil.tension import normaliser

log = logging.getLogger("loeil.missions")

FUSEAU = ZoneInfo("Europe/Paris")
EN_COURS, ACCOMPLIE, RATEE = "en_cours", "ok", "ko"
MAX_JOURS_GARDES = 14

# Retourne {membre_id: pseudo} des présents (et peut-être) du sondage du soir.
ChargerPresents = Callable[[date], Awaitable[tuple[dict[int, str], dict[int, str]] | None]]


# --- Logique pure ------------------------------------------------------------------

def date_soiree(maintenant: datetime) -> date:
    """La soirée RP déborde après minuit : avant midi, on parle encore de la veille."""
    maintenant = maintenant.astimezone(FUSEAU)
    return (maintenant - timedelta(days=1)).date() if maintenant.hour < 12 else maintenant.date()


def texte_modele(noms: list[str]) -> str:
    return "\n".join(f"{nom} : " for nom in noms)


def _cle(nom: str) -> str:
    return normaliser(nom).lstrip("@").strip()


def associer_missions(texte: str, membres: dict[int, str]) -> tuple[dict[int, str], list[str]]:
    """Lit les lignes « Pseudo : mission ». Retourne ({id: mission}, lignes non comprises)."""
    par_nom = {_cle(nom): membre_id for membre_id, nom in membres.items()}
    attributions: dict[int, str] = {}
    inconnues: list[str] = []
    for ligne in texte.splitlines():
        if not ligne.strip():
            continue
        nom, sep, mission = ligne.partition(":")
        mission = mission.strip()
        if not sep:
            inconnues.append(ligne.strip())
            continue
        if not mission:
            continue  # pseudo laissé sans mission : on ne lui envoie rien
        cle = _cle(nom)
        membre_id = par_nom.get(cle)
        if membre_id is None:
            candidats = [i for n, i in par_nom.items() if n.startswith(cle) and cle]
            membre_id = candidats[0] if len(candidats) == 1 else None
        if membre_id is None:
            inconnues.append(ligne.strip())
        else:
            attributions[membre_id] = mission
    return attributions, inconnues


class StockageMissions:
    """Missions par soirée : {date: {membre_id: {nom, mission, par, statut, commentaire}}}."""

    def __init__(self, chemin: Path):
        self.chemin = chemin
        self.donnees: dict[str, dict[str, dict]] = {}
        if chemin.exists():
            try:
                self.donnees = json.loads(chemin.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.error("Fichier %s illisible, on repart de zéro", chemin)

    def soiree(self, jour: date) -> dict[str, dict]:
        return self.donnees.get(jour.isoformat(), {})

    def ajouter(self, jour: date, membre_id: int, nom: str, mission: str, par: str) -> None:
        self.donnees.setdefault(jour.isoformat(), {})[str(membre_id)] = {
            "nom": nom, "mission": mission, "par": par, "statut": EN_COURS, "commentaire": "",
        }
        for ancien in sorted(self.donnees)[:-MAX_JOURS_GARDES]:
            del self.donnees[ancien]
        self.sauver()

    def statuer(self, jour: date, membre_id: int, statut: str, commentaire: str = "",
                mission: str = "", nom: str = "") -> None:
        soiree = self.donnees.setdefault(jour.isoformat(), {})
        entree = soiree.setdefault(str(membre_id), {"nom": nom, "mission": mission, "par": "?",
                                                    "statut": EN_COURS, "commentaire": ""})
        entree["statut"] = statut
        entree["commentaire"] = commentaire
        self.sauver()

    def sauver(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.chemin.write_text(json.dumps(self.donnees, ensure_ascii=False, indent=1), encoding="utf-8")


def lignes_rapport(missions: dict[str, dict], presents: dict[int, str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """(accomplies, ratées, sans réponse, présents sans mission) prêts à afficher."""
    ok, ko, attente = [], [], []
    for entree in missions.values():
        ligne = f"**{entree['nom']}** — {entree['mission']}"
        if entree["statut"] == ACCOMPLIE:
            ok.append(ligne)
        elif entree["statut"] == RATEE:
            ko.append(ligne + (f" _({entree['commentaire']})_" if entree["commentaire"] else ""))
        else:
            attente.append(ligne)
    sans_mission = [nom for membre_id, nom in presents.items() if str(membre_id) not in missions]
    return ok, ko, attente, sans_mission


def _champ(lignes: list[str]) -> str:
    texte = "\n".join(lignes) if lignes else "—"
    return texte if len(texte) <= 1024 else texte[:1000] + "\n…"


def embed_rapport(jour: date, missions: dict[str, dict], presents: dict[int, str]) -> discord.Embed:
    ok, ko, attente, sans_mission = lignes_rapport(missions, presents)
    embed = discord.Embed(
        title=f"📑 Rapport de la soirée du {jour:%d/%m}",
        description=f"{len(missions)} mission(s) données · {len(presents)} présent(s) déclaré(s)",
        color=discord.Color.dark_teal(),
    )
    embed.add_field(name=f"✅ Accomplies ({len(ok)})", value=_champ(ok), inline=False)
    embed.add_field(name=f"❌ Pas faites ({len(ko)})", value=_champ(ko), inline=False)
    embed.add_field(name=f"⏳ Sans réponse ({len(attente)})", value=_champ(attente), inline=False)
    embed.add_field(name=f"👤 Présents sans mission ({len(sans_mission)})", value=_champ(sans_mission), inline=False)
    return embed


# --- Discord ------------------------------------------------------------------------

def embed_mission(jour: date, mission: str, par: str, statut: str = EN_COURS, commentaire: str = "") -> discord.Embed:
    couleurs = {EN_COURS: discord.Color.gold(), ACCOMPLIE: discord.Color.green(), RATEE: discord.Color.red()}
    embed = discord.Embed(title="🎯 Ta mission de ce soir", description=mission, color=couleurs[statut])
    embed.add_field(name="Donnée par", value=par, inline=True)
    if statut == ACCOMPLIE:
        embed.add_field(name="Statut", value="✅ Accomplie", inline=True)
    elif statut == RATEE:
        embed.add_field(name="Statut", value="❌ Pas faite" + (f" — {commentaire}" if commentaire else ""), inline=False)
    embed.set_footer(text=f"Soirée du {jour.isoformat()} · L'Œil")
    return embed


def _jour_depuis_embed(embed: discord.Embed) -> date:
    texte = embed.footer.text or ""
    try:
        return date.fromisoformat(texte.split("Soirée du ")[1][:10])
    except (IndexError, ValueError):
        return date_soiree(datetime.now(FUSEAU))


def _infos_depuis_embed(embed: discord.Embed) -> tuple[str, str]:
    par = next((f.value for f in embed.fields if f.name == "Donnée par"), "?")
    return embed.description or "", par


class ModalRaison(discord.ui.Modal, title="Mission pas faite"):
    raison = discord.ui.TextInput(label="Pourquoi ? (facultatif)", required=False, max_length=300)

    def __init__(self, stockage: StockageMissions):
        super().__init__()
        self.stockage = stockage

    async def on_submit(self, interaction: discord.Interaction) -> None:
        embed = interaction.message.embeds[0]
        jour = _jour_depuis_embed(embed)
        mission, par = _infos_depuis_embed(embed)
        commentaire = str(self.raison.value).strip()
        self.stockage.statuer(jour, interaction.user.id, RATEE, commentaire, mission, interaction.user.display_name)
        await interaction.response.edit_message(embed=embed_mission(jour, mission, par, RATEE, commentaire), view=None)


class VueMission(discord.ui.View):
    """Boutons sous la mission reçue en MP (persistants)."""

    def __init__(self, stockage: StockageMissions):
        super().__init__(timeout=None)
        self.stockage = stockage

    @discord.ui.button(label="Accomplie", emoji="✅", style=discord.ButtonStyle.success, custom_id="mission:ok")
    async def accomplie(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        embed = interaction.message.embeds[0]
        jour = _jour_depuis_embed(embed)
        mission, par = _infos_depuis_embed(embed)
        self.stockage.statuer(jour, interaction.user.id, ACCOMPLIE, "", mission, interaction.user.display_name)
        await interaction.response.edit_message(embed=embed_mission(jour, mission, par, ACCOMPLIE), view=None)

    @discord.ui.button(label="Pas pu la faire", emoji="❌", style=discord.ButtonStyle.danger, custom_id="mission:ko")
    async def ratee(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(ModalRaison(self.stockage))


async def envoyer_mission(client: discord.Client, stockage: StockageMissions, jour: date,
                          membre_id: int, nom: str, mission: str, par: str) -> bool:
    try:
        utilisateur = client.get_user(membre_id) or await client.fetch_user(membre_id)
        await utilisateur.send(embed=embed_mission(jour, mission, par), view=VueMission(stockage))
    except discord.HTTPException as exc:
        log.warning("Mission non envoyée à %s : %s", nom, exc)
        return False
    stockage.ajouter(jour, membre_id, nom, mission, par)
    return True


class ModalMissions(discord.ui.Modal, title="Missions du soir"):
    def __init__(self, client: discord.Client, stockage: StockageMissions, jour: date, presents: dict[int, str]):
        super().__init__()
        self.client, self.stockage, self.jour, self.presents = client, stockage, jour, presents
        self.texte = discord.ui.TextInput(
            label="Une ligne par joueur : Pseudo : mission",
            style=discord.TextStyle.paragraph,
            default=texte_modele(list(presents.values()))[:4000],
            max_length=4000,
        )
        self.add_item(self.texte)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        attributions, inconnues = associer_missions(str(self.texte.value), self.presents)
        envoyees, echecs = [], []
        for membre_id, mission in attributions.items():
            nom = self.presents[membre_id]
            ok = await envoyer_mission(self.client, self.stockage, self.jour, membre_id, nom, mission,
                                       interaction.user.display_name)
            (envoyees if ok else echecs).append(nom)
        lignes = [f"✅ {len(envoyees)} mission(s) envoyée(s) en MP" + (f" : {', '.join(envoyees)}" if envoyees else "")]
        if echecs:
            lignes.append(f"⚠️ MP fermés, à prévenir toi-même : {', '.join(echecs)}")
        if inconnues:
            lignes.append("❓ Lignes non comprises (pseudo introuvable ou « : » manquant) :\n" +
                          "\n".join(f"• {l}" for l in inconnues[:15]))
        await interaction.followup.send("\n".join(lignes)[:2000])


class VueAttribution(discord.ui.View):
    """Bouton envoyé aux chefs à 20h (persistant)."""

    def __init__(self, client: discord.Client, stockage: StockageMissions, charger_presents: ChargerPresents):
        super().__init__(timeout=None)
        self.client, self.stockage, self.charger_presents = client, stockage, charger_presents

    @discord.ui.button(label="Attribuer les missions", emoji="📝", style=discord.ButtonStyle.primary,
                       custom_id="missions:attribuer")
    async def attribuer(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id not in config.MISSIONS_CHEF_IDS:
            await interaction.response.send_message("Réservé aux chefs.", ephemeral=True)
            return
        jour = date_soiree(datetime.now(FUSEAU))
        resultat = await self.charger_presents(jour)
        if not resultat or not (resultat[0] or resultat[1]):
            await interaction.response.send_message("Personne n'est déclaré présent ce soir.")
            return
        presents, peut_etre = resultat
        await interaction.response.send_modal(
            ModalMissions(self.client, self.stockage, jour, {**presents, **peut_etre})
        )


def embed_presents(jour: date, presents: dict[int, str], peut_etre: dict[int, str]) -> discord.Embed:
    embed = discord.Embed(
        title=f"🎯 Présents ce soir — {jour:%d/%m}",
        description="Clique sur **Attribuer les missions** : écris la mission de chacun après les « : ». "
                    "Laisse vide pour ne rien envoyer à quelqu'un.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name=f"✅ Présents ({len(presents)})", value=_champ(list(presents.values())), inline=True)
    embed.add_field(name=f"⏳ Peut-être ({len(peut_etre)})", value=_champ(list(peut_etre.values())), inline=True)
    return embed
