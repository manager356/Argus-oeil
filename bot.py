import asyncio
import logging
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks

from loeil import apaisement, bilan, config, faits_armes, missions, reglages, strategie
from loeil.annonces import MemoireAnnonces, contenu_message
from loeil.discussion import Discussion
from loeil.presence import StockageVotes, VuePresence, publier_sondage, votes_du_jour


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("loeil.bot")

FUSEAU = ZoneInfo("Europe/Paris")
_heure, _minute = (int(x) for x in config.PRESENCE_HOUR.split(":"))
_stockage_presence = StockageVotes(Path(__file__).parent / "donnees" / "presence.json")
_stockage_missions = missions.StockageMissions(Path(__file__).parent / "donnees" / "missions.json")
_messages_suivi: dict[str, discord.Message] = {}
_reglages = reglages.Reglages()
_verrou_suivi = asyncio.Lock()
# Salons d'infos que L'Œil lit pour répondre : id du salon -> (nom de la partie, mémoire)
_salons_infos: dict[int, tuple[str, MemoireAnnonces]] = {}
if config.ANNONCES_CHANNEL_ID:
    _salons_infos[config.ANNONCES_CHANNEL_ID] = ("annonces", MemoireAnnonces(taille=30, max_caracteres=1500))
if config.BILANS_CHANNEL_ID:
    _salons_infos[config.BILANS_CHANNEL_ID] = ("bilans_reunions", MemoireAnnonces(taille=12, max_caracteres=8000))
if config.OBJECTIFS_CHANNEL_ID:
    _salons_infos[config.OBJECTIFS_CHANNEL_ID] = ("objectifs", MemoireAnnonces(taille=20, max_caracteres=3000))
if config.MEMOIRE_CHANNEL_ID:
    _salons_infos[config.MEMOIRE_CHANNEL_ID] = ("memoire", MemoireAnnonces(taille=100, max_caracteres=1500))
_discussion = Discussion({titre: memoire for titre, memoire in _salons_infos.values()})


_intents = discord.Intents.default()
_intents.message_content = True


class LoeilClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=_intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.add_view(VuePresence(_stockage_presence))
        self.add_view(missions.VueMission(_stockage_missions))
        self.add_view(missions.VueAttribution(self, _stockage_missions, charger_presents))
        if config.MISSIONS_CHEF_IDS:
            envoi_presents.start()
            relance_missions.start()
            rapport_missions.start()
            log.info("Missions : présents à %s, relance à %s, rapport à %s",
                     config.MISSIONS_HOUR, config.RELANCE_HOUR, config.RAPPORT_HOUR)
        if config.PRESENCE_CHANNEL_ID:
            sondage_quotidien.start()
            log.info("Sondage de présence programmé à %s", config.PRESENCE_HOUR)
        else:
            log.warning("PRESENCE_CHANNEL_ID vide : sondage de présence désactivé")
        if config.TENSION_CHANNEL_IDS:
            log.info("Apaisement actif sur %d salon(s)", len(config.TENSION_CHANNEL_IDS))
        else:
            log.warning("TENSION_CHANNEL_IDS vide : apaisement des tensions désactivé")

        if config.GUILD_ID is not None:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands synchronisées sur le serveur %s", config.GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Slash commands synchronisées globalement (peut prendre jusqu'à 1h)")


bot = LoeilClient()


async def poster_sondage() -> discord.Message | None:
    salon = bot.get_channel(config.PRESENCE_CHANNEL_ID or 0)
    if salon is None:
        log.warning("Sondage non posté : salon %s introuvable", config.PRESENCE_CHANNEL_ID)
        return None
    return await publier_sondage(salon, _stockage_presence, datetime.now(FUSEAU).date(),
                                 config.PRESENCE_ROLE_ID or 0)


@tasks.loop(time=time(hour=_heure, minute=_minute, tzinfo=FUSEAU))
async def sondage_quotidien() -> None:
    try:
        await poster_sondage()
    except discord.HTTPException as exc:
        log.error("Échec du sondage de présence : %s", exc)


@sondage_quotidien.before_loop
async def _attendre_connexion() -> None:
    await bot.wait_until_ready()


def _heure(texte: str) -> time:
    h, m = (int(x) for x in texte.split(":"))
    return time(hour=h, minute=m, tzinfo=FUSEAU)


async def charger_presents(jour) -> tuple[dict[int, str], dict[int, str]] | None:
    """({id: pseudo} des présents, {id: pseudo} des peut-être) pour le sondage du jour donné."""
    votes = await charger_votes_noms(jour)
    return (votes["present"], votes["peutetre"]) if votes else None


async def resume_presence() -> str:
    """Résultat du sondage du soir, donné à L'Œil pour répondre à « qui est dispo ce soir ? »."""
    jour = missions.date_soiree(datetime.now(FUSEAU))
    votes = await charger_votes_noms(jour)
    if votes is None:
        return "<presence_du_soir>Pas encore de sondage de présence pour ce soir (il est posté à " \
               f"{config.PRESENCE_HOUR}).</presence_du_soir>"
    lignes = [f"Sondage de présence du {jour:%d/%m} :"]
    for cle, libelle in (("present", "Présents"), ("peutetre", "Peut-être / en retard"), ("absent", "Absents")):
        noms = list(votes[cle].values())
        lignes.append(f"- {libelle} ({len(noms)}) : {', '.join(noms) if noms else 'personne'}")
    lignes.append("Ceux qui n'apparaissent pas n'ont pas encore voté.")
    return "<presence_du_soir>\n" + "\n".join(lignes) + "\n</presence_du_soir>"


async def charger_votes_noms(jour) -> dict[str, dict[int, str]] | None:
    """{choix: {id: pseudo}} pour le sondage du jour donné."""
    salon = bot.get_channel(config.PRESENCE_CHANNEL_ID or 0)
    if salon is None or bot.user is None:
        return None
    votes = await votes_du_jour(salon, _stockage_presence, jour, bot.user.id)
    if votes is None:
        return None

    async def noms(ids: list[int]) -> dict[int, str]:
        resultat = {}
        for membre_id in ids:
            membre = salon.guild.get_member(membre_id)
            if membre is None:
                try:
                    membre = await salon.guild.fetch_member(membre_id)
                except discord.HTTPException:
                    resultat[membre_id] = f"Membre {membre_id}"
                    continue
            resultat[membre_id] = membre.display_name
        return resultat

    return {cle: await noms(ids) for cle, ids in votes.items()}


async def statut_presence(membre_id: int) -> str | None:
    """Ce que le membre a voté au sondage du soir (present / absent / peutetre), ou None."""
    salon = bot.get_channel(config.PRESENCE_CHANNEL_ID or 0)
    if salon is None or bot.user is None:
        return None
    jour = missions.date_soiree(datetime.now(FUSEAU))
    votes = await votes_du_jour(salon, _stockage_presence, jour, bot.user.id)
    if votes is None:
        return None
    return next((cle for cle, ids in votes.items() if membre_id in ids), None)


_discussion.statut_presence = statut_presence
_discussion.resume_presence = resume_presence


async def _trouver_suivi(salon: discord.abc.Messageable, jour) -> discord.Message | None:
    if jour.isoformat() in _messages_suivi:
        return _messages_suivi[jour.isoformat()]
    async for message in salon.history(limit=100):
        if message.author == bot.user and message.embeds and missions.jour_du_suivi(message.embeds[0]) == jour:
            _messages_suivi[jour.isoformat()] = message
            return message
    return None


async def synchroniser_suivi(jour) -> None:
    """Met à jour (ou crée) le message de suivi des missions dans le salon staff : c'est lui qui fait foi."""
    salon = bot.get_channel(config.TENSION_STAFF_CHANNEL_ID or 0)
    if salon is None:
        return
    async with _verrou_suivi:  # les changements s'appliquent dans l'ordre, l'état final est toujours le bon
        embed = missions.embed_suivi(jour, _stockage_missions.soiree(jour))
        try:
            message = await _trouver_suivi(salon, jour)
            if message is None:
                _messages_suivi[jour.isoformat()] = await salon.send(embed=embed)
            else:
                await message.edit(embed=embed)
        except discord.HTTPException as exc:
            log.error("Suivi des missions non mis à jour : %s", exc)


def _au_changement_missions(jour) -> None:
    asyncio.create_task(synchroniser_suivi(jour))


_stockage_missions.au_changement = _au_changement_missions


async def restaurer_suivi() -> None:
    """Au démarrage : relit le suivi de la soirée en cours depuis Discord (les fichiers ne survivent pas)."""
    salon = bot.get_channel(config.TENSION_STAFF_CHANNEL_ID or 0)
    if salon is None:
        return
    jour = missions.date_soiree(datetime.now(FUSEAU))
    try:
        message = await _trouver_suivi(salon, jour)
    except discord.HTTPException as exc:
        log.error("Lecture du suivi des missions impossible : %s", exc)
        return
    if message is None:
        return
    soiree = missions.lire_suivi(message.embeds[0])
    if len(soiree) >= len(_stockage_missions.soiree(jour)):
        _stockage_missions.restaurer(jour, soiree)
        log.info("Suivi des missions restauré depuis Discord : %d mission(s)", len(soiree))


async def mission_du_joueur(membre_id: int) -> str:
    jour = missions.date_soiree(datetime.now(FUSEAU))
    entree = _stockage_missions.soiree(jour).get(str(membre_id))
    if entree:
        return entree["mission"]
    # Missions perdues après un redéploiement : le récap des annonces fait foi.
    return "aucune mission enregistrée pour lui (regarde le récap « Missions du soir » dans les annonces)"


async def signaler_refus(membre: discord.abc.User) -> None:
    """Refus d'ordre confirmé : on l'enregistre et on prévient les chefs + le salon staff."""
    jour = missions.date_soiree(datetime.now(FUSEAU))
    entree = _stockage_missions.soiree(jour).get(str(membre.id))
    if entree is None:  # missions perdues (redéploiement sans Volume) : on signale quand même
        entree = {"nom": membre.display_name, "mission": "(voir le récap des missions dans les annonces)", "par": "?"}
    _stockage_missions.statuer(jour, membre.id, missions.REFUS, mission=entree["mission"], nom=entree["nom"])
    embed = discord.Embed(
        title="🚫 Refus d'ordre",
        description=f"{membre.mention} (**{entree['nom']}**) a refusé sa mission et a confirmé.",
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="Mission", value=entree["mission"][:1024], inline=False)
    embed.add_field(name="Donnée par", value=entree["par"], inline=True)
    cibles = []
    salon_staff = bot.get_channel(config.TENSION_STAFF_CHANNEL_ID or 0)
    if salon_staff:
        cibles.append(salon_staff)
    for chef_id in config.MISSIONS_CHEF_IDS:
        try:
            cibles.append(bot.get_user(chef_id) or await bot.fetch_user(chef_id))
        except discord.HTTPException:
            pass
    for cible in cibles:
        try:
            await cible.send(embed=embed)
        except discord.HTTPException as exc:
            log.error("Refus d'ordre non signalé à %s : %s", cible, exc)


_discussion.mission_du_joueur = mission_du_joueur
_discussion.signaler_refus = signaler_refus


async def noter(note: str, auteur: str) -> bool:
    """Écrit une note dans #mémoire-oeil ; on_message la range ensuite dans la mémoire de L'Œil."""
    salon = bot.get_channel(config.MEMOIRE_CHANNEL_ID or 0)
    if salon is None:
        log.warning("Salon mémoire %s introuvable", config.MEMOIRE_CHANNEL_ID)
        return False
    try:
        await salon.send(f"📌 {note}\n-# noté à la demande de {auteur}",
                         allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException as exc:
        log.error("Note non écrite dans la mémoire : %s", exc)
        return False
    return True


_discussion.noter = noter


async def envoyer_presents_aux_chefs(destinataires: list[int]) -> str:
    jour = missions.date_soiree(datetime.now(FUSEAU))
    resultat = await charger_presents(jour)
    if resultat is None:
        return "Pas de sondage de présence trouvé pour ce soir."
    presents, peut_etre = resultat
    embed = missions.embed_presents(jour, presents, peut_etre)
    envoyes = 0
    for chef_id in destinataires:
        try:
            chef = bot.get_user(chef_id) or await bot.fetch_user(chef_id)
            await chef.send(embed=embed, view=missions.VueAttribution(bot, _stockage_missions, charger_presents))
            envoyes += 1
        except discord.HTTPException as exc:
            log.error("Liste des présents non envoyée à %s : %s", chef_id, exc)
    if not envoyes:
        return "Impossible d'envoyer le MP (MP fermés ?)."
    return f"Liste envoyée en MP ({len(presents)} présent(s), {len(peut_etre)} peut-être)."


async def analyse_strategique(sujet: str = "") -> str | None:
    """Stratégies de L'Œil sur les points à suivre (tous, ou un sujet précis)."""
    return await strategie.generer_strategie(_discussion.client, _discussion.texte_sources(),
                                             await resume_presence(), sujet)


async def envoyer_strategie_aux_chefs(destinataires: list[int]) -> None:
    texte = await analyse_strategique()
    if not texte:
        return
    morceaux = bilan.decouper("🧠 **Analyse stratégique du soir**\n\n" + texte)
    for chef_id in destinataires:
        try:
            chef = bot.get_user(chef_id) or await bot.fetch_user(chef_id)
            for morceau in morceaux:
                await chef.send(morceau)
        except discord.HTTPException as exc:
            log.error("Analyse stratégique non envoyée à %s : %s", chef_id, exc)


@tasks.loop(time=_heure(config.MISSIONS_HOUR))
async def envoi_presents() -> None:
    log.info(await envoyer_presents_aux_chefs(config.MISSIONS_CHEF_IDS))
    if config.STRATEGIE_20H:
        await envoyer_strategie_aux_chefs(config.MISSIONS_CHEF_IDS)


@tasks.loop(time=_heure(config.RELANCE_HOUR))
async def relance_missions() -> None:
    jour = missions.date_soiree(datetime.now(FUSEAU))
    relances, echecs = await missions.relancer(bot, _stockage_missions, jour)
    log.info("Relance missions : %d relancé(s), %d MP fermé(s)", len(relances), len(echecs))


@relance_missions.before_loop
async def _attendre_avant_relance() -> None:
    await bot.wait_until_ready()


@tasks.loop(time=_heure(config.RAPPORT_HOUR))
async def rapport_missions() -> None:
    jour = missions.date_soiree(datetime.now(FUSEAU))
    soiree = _stockage_missions.soiree(jour)
    resultat = await charger_presents(jour)
    presents = {**resultat[0], **resultat[1]} if resultat else {}
    if not soiree and not presents:
        return
    embed = missions.embed_rapport(jour, soiree, presents)
    salon_staff = bot.get_channel(config.TENSION_STAFF_CHANNEL_ID or 0)
    cibles = [salon_staff] if salon_staff else []
    for chef_id in config.MISSIONS_CHEF_IDS:
        try:
            cibles.append(bot.get_user(chef_id) or await bot.fetch_user(chef_id))
        except discord.HTTPException:
            pass
    for cible in cibles:
        try:
            await cible.send(embed=embed)
        except discord.HTTPException as exc:
            log.error("Rapport non envoyé à %s : %s", cible, exc)


@envoi_presents.before_loop
async def _attendre_avant_presents() -> None:
    await bot.wait_until_ready()


@rapport_missions.before_loop
async def _attendre_avant_rapport() -> None:
    await bot.wait_until_ready()


@bot.tree.command(name="missions", description="Recevoir maintenant en MP la liste des présents pour donner les missions.")
@app_commands.default_permissions(manage_guild=True)
async def commande_missions(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(await envoyer_presents_aux_chefs([interaction.user.id]), ephemeral=True)


@bot.tree.command(name="mission", description="Donner une mission à un joueur (envoyée en MP).")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(joueur="Le joueur", mission="La mission à lui confier")
async def commande_mission(interaction: discord.Interaction, joueur: discord.Member, mission: str) -> None:
    await interaction.response.defer(ephemeral=True)
    jour = missions.date_soiree(datetime.now(FUSEAU))
    ok = await missions.envoyer_mission(bot, _stockage_missions, jour, joueur.id, joueur.display_name,
                                        mission, interaction.user.display_name)
    texte = (f"Mission envoyée en MP à {joueur.display_name}." if ok
             else f"Impossible d'envoyer un MP à {joueur.display_name} (MP fermés).")
    await interaction.followup.send(texte, ephemeral=True)


@bot.tree.command(name="rapport-missions", description="Voir maintenant le rapport des missions de la soirée.")
@app_commands.default_permissions(manage_guild=True)
async def commande_rapport(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    jour = missions.date_soiree(datetime.now(FUSEAU))
    resultat = await charger_presents(jour)
    presents = {**resultat[0], **resultat[1]} if resultat else {}
    embed = missions.embed_rapport(jour, _stockage_missions.soiree(jour), presents)
    await interaction.followup.send(embed=embed, ephemeral=True)


async def contexte_missions(jour) -> str:
    """Missions de la soirée et leur issue, pour enrichir le bilan."""
    libelles = {missions.ACCOMPLIE: "accomplie", missions.RATEE: "pas faite", missions.REFUS: "REFUS D'ORDRE",
                missions.EN_COURS: "sans réponse"}
    lignes = []
    for entree in _stockage_missions.soiree(jour).values():
        ligne = f"- {entree['nom']} : {entree['mission']} → {libelles.get(entree['statut'], entree['statut'])}"
        if entree.get("commentaire"):
            ligne += f" ({entree['commentaire']})"
        lignes.append(ligne)
    return "\n".join(lignes)


@bot.tree.command(name="strategie", description="L'Œil propose des stratégies pour les points à suivre.")
@app_commands.describe(sujet="Un sujet précis (ex. Cabra, Kanan). Vide = tous les points ouverts.")
async def commande_strategie(interaction: discord.Interaction, sujet: str = "") -> None:
    if not bilan.peut_faire_un_bilan(interaction.user):
        await interaction.response.send_message("Réservé au staff et aux leads.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    texte = await analyse_strategique(sujet.strip())
    if not texte:
        await interaction.followup.send("Je n'ai pas réussi à produire l'analyse. Réessaie dans un instant.",
                                        ephemeral=True)
        return
    for morceau in bilan.decouper(texte):
        await interaction.followup.send(morceau, ephemeral=True)


@bot.tree.command(name="clore", description="Marquer un point à suivre comme réglé (L'Œil n'en parlera plus).")
@app_commands.describe(point="Le point réglé (ex. « Kanan libéré », « dette des Chapeaux blancs payée »)")
async def commande_clore(interaction: discord.Interaction, point: str) -> None:
    if not bilan.peut_faire_un_bilan(interaction.user):
        await interaction.response.send_message("Réservé au staff et aux leads.", ephemeral=True)
        return
    jour = datetime.now(FUSEAU)
    ok = await noter(f"✅ Point clos le {jour:%d/%m} : {point}", interaction.user.display_name)
    await interaction.response.send_message(
        "Noté, point clos." if ok else "Je n'ai pas pu l'écrire dans #mémoire-oeil (permissions ?).",
        ephemeral=True)


@bot.tree.command(name="bilan", description="Donner tes notes de la soirée : L'Œil rédige le bilan complet.")
async def commande_bilan(interaction: discord.Interaction) -> None:
    if not bilan.peut_faire_un_bilan(interaction.user):
        await interaction.response.send_message("Réservé au staff et aux leads.", ephemeral=True)
        return
    jour = missions.date_soiree(datetime.now(FUSEAU))
    await interaction.response.send_modal(bilan.ModalBilan(_discussion.client, jour, contexte_missions))


def programmer_sondage(heure: str) -> None:
    """Change l'heure du sondage quotidien et relance la tâche pour que ce soit pris en compte tout de suite."""
    sondage_quotidien.change_interval(time=_heure(heure))
    if sondage_quotidien.is_running():
        sondage_quotidien.restart()
    else:
        sondage_quotidien.start()
    log.info("Sondage de présence programmé à %s", heure)


async def appliquer_reglages() -> None:
    """Au démarrage : relit les réglages gardés dans discu boss (ex. heure du sondage choisie par commande)."""
    salon = bot.get_channel(config.TENSION_STAFF_CHANNEL_ID or 0)
    if salon is None or bot.user is None:
        return
    try:
        await _reglages.charger(salon, bot.user.id)
    except discord.HTTPException as exc:
        log.error("Lecture des réglages impossible : %s", exc)
        return
    heure = _reglages.valeurs.get("heure_sondage")
    if heure and config.PRESENCE_CHANNEL_ID:
        programmer_sondage(heure)


@bot.tree.command(name="heure-sondage", description="Choisir l'heure du sondage de présence quotidien.")
@app_commands.describe(heure="Ex. 18h, 18:30, 21h")
async def commande_heure_sondage(interaction: discord.Interaction, heure: str) -> None:
    if not bilan.peut_faire_un_bilan(interaction.user):
        await interaction.response.send_message("Réservé au staff et aux leads.", ephemeral=True)
        return
    valeur = reglages.heure_valide(heure)
    if valeur is None:
        await interaction.response.send_message("Heure invalide. Exemples : `18h`, `18:30`, `21h`.", ephemeral=True)
        return
    salon = bot.get_channel(config.TENSION_STAFF_CHANNEL_ID or 0)
    if salon is None:
        await interaction.response.send_message("Salon staff introuvable pour garder le réglage.", ephemeral=True)
        return
    try:
        await _reglages.definir(salon, "heure_sondage", valeur)
    except discord.HTTPException as exc:
        await interaction.response.send_message(f"Réglage non enregistré : {exc}", ephemeral=True)
        return
    programmer_sondage(valeur)
    await interaction.response.send_message(
        f"C'est noté : le sondage de présence partira chaque jour à **{valeur}** (heure de Paris).", ephemeral=True)


_dernier_faits_armes: dict[int, float] = {}
LIBELLES_STATUT = {missions.ACCOMPLIE: "accomplie", missions.RATEE: "pas faite", missions.REFUS: "REFUS D'ORDRE",
                   missions.EN_COURS: "sans réponse"}


async def archives_de(nom: str) -> tuple[str, str]:
    """(extraits d'archives qui citent le membre, historique de ses missions)."""
    sources = [(config.BILANS_CHANNEL_ID, "Bilan", 500), (config.MEMOIRE_CHANNEL_ID, "Mémoire", 500),
               (config.ANNONCES_CHANNEL_ID, "Annonce", 300), (config.OBJECTIFS_CHANNEL_ID, "Objectif", 200)]
    extraits: list[faits_armes.Extrait] = []
    for salon_id, libelle, limite in sources:
        salon = bot.get_channel(salon_id or 0)
        if salon is None:
            continue
        try:
            async for m in salon.history(limit=limite):
                texte = contenu_message(m)
                if texte and faits_armes.cite(texte, nom):
                    extraits.append(faits_armes.Extrait(m.created_at, libelle, m.author.display_name, texte))
        except discord.HTTPException as exc:
            log.warning("Archives %s illisibles : %s", libelle, exc)

    lignes_missions = []
    salon_staff = bot.get_channel(config.TENSION_STAFF_CHANNEL_ID or 0)
    if salon_staff is not None:
        try:
            async for m in salon_staff.history(limit=1500):
                if m.author != bot.user or not m.embeds:
                    continue
                jour = missions.jour_du_suivi(m.embeds[0])
                if jour is None:
                    continue
                for entree in missions.lire_suivi(m.embeds[0]).values():
                    if faits_armes.cite(entree["nom"], nom):
                        ligne = (f"- {jour:%d/%m} — {entree['nom']} : {entree['mission']} → "
                                 f"{LIBELLES_STATUT.get(entree['statut'], entree['statut'])}")
                        if entree.get("commentaire"):
                            ligne += f" ({entree['commentaire']})"
                        lignes_missions.append(ligne)
        except discord.HTTPException as exc:
            log.warning("Suivi des missions illisible : %s", exc)
    return faits_armes.formater_extraits(extraits), "\n".join(reversed(lignes_missions))


@bot.tree.command(name="faits-armes", description="Les faits d'armes d'un membre d'Argus, d'après les archives de L'Œil.")
@app_commands.describe(membre="Le nom du perso (ex. Kanan, Diego, Rosita)")
async def commande_faits_armes(interaction: discord.Interaction, membre: str) -> None:
    maintenant = datetime.now().timestamp()
    if not bilan.peut_faire_un_bilan(interaction.user) and \
            maintenant - _dernier_faits_armes.get(interaction.user.id, 0) < 120:
        await interaction.response.send_message("Patience. Une recherche toutes les 2 minutes.", ephemeral=True)
        return
    _dernier_faits_armes[interaction.user.id] = maintenant
    await interaction.response.defer(thinking=True)
    archives, historique = await archives_de(membre.strip())
    texte = await faits_armes.rediger(_discussion.client, membre.strip(), archives, historique)
    if not texte:
        await interaction.followup.send("Les archives restent muettes pour l'instant. Réessaie dans un instant.")
        return
    for morceau in bilan.decouper(texte):
        await interaction.followup.send(morceau, allowed_mentions=discord.AllowedMentions.none())


@bot.tree.command(name="sondage-presence", description="Poster le sondage de présence maintenant.")
@app_commands.default_permissions(manage_guild=True)
async def sondage_presence(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        message = await poster_sondage()
    except discord.Forbidden:
        log.exception("Permission refusée pour poster le sondage")
        await interaction.followup.send(
            "Je n'ai pas le droit de poster dans le salon du sondage. Donne au rôle de L'Œil : "
            "Voir le salon, Envoyer des messages, Intégrer des liens, Mentionner tout le monde.",
            ephemeral=True,
        )
        return
    except discord.HTTPException as exc:
        log.exception("Échec du sondage de présence")
        await interaction.followup.send(f"Échec du sondage : {exc}", ephemeral=True)
        return
    if message is None:
        await interaction.followup.send("Salon du sondage introuvable : vérifie PRESENCE_CHANNEL_ID.", ephemeral=True)
    else:
        await interaction.followup.send(f"Sondage posté : {message.jump_url}", ephemeral=True)


@bot.event
async def on_ready() -> None:
    log.info("L'Œil est connecté en tant que %s (id=%s)", bot.user, bot.user.id if bot.user else "?")
    await restaurer_suivi()
    await appliquer_reglages()
    for salon_id, (titre, memoire) in _salons_infos.items():
        salon = bot.get_channel(salon_id)
        if salon is None:
            log.warning("Salon d'infos %s (%s) introuvable ou invisible pour L'Œil", salon_id, titre)
            continue
        try:
            await memoire.charger(salon)
        except discord.HTTPException as exc:
            log.error("Lecture de %s impossible : %s", titre, exc)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.guild is None:
        return
    # Les annonces sont parfois postées par des bots (ou par L'Œil, ex. récap des missions) : on les lit.
    if message.channel.id in _salons_infos:
        _salons_infos[message.channel.id][1].ajouter_message(message)
        return
    if message.author.bot:
        return
    await apaisement.on_guild_message(bot, message)
    if config.CHAT_ENABLED and bot.user is not None:
        a_traiter, directe = _discussion.doit_considerer(message, bot.user)
        if a_traiter:
            if directe:
                async with message.channel.typing():
                    await _discussion.repondre(message, bot.user, directe)
            else:
                await _discussion.repondre(message, bot.user, directe)


@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent) -> None:
    # Une note de mémoire (ou une annonce) supprimée : L'Œil l'oublie.
    if payload.channel_id in _salons_infos:
        titre, memoire = _salons_infos[payload.channel_id]
        salon = bot.get_channel(payload.channel_id)
        if salon is not None:
            try:
                await memoire.charger(salon)
            except discord.HTTPException as exc:
                log.error("Relecture de %s impossible : %s", titre, exc)


@bot.event
async def on_message_edit(avant: discord.Message, apres: discord.Message) -> None:
    # Une annonce ou un bilan corrigé : on recharge pour garder la bonne version.
    if apres.channel.id in _salons_infos:
        titre, memoire = _salons_infos[apres.channel.id]
        try:
            await memoire.charger(apres.channel)
        except discord.HTTPException as exc:
            log.error("Relecture de %s impossible : %s", titre, exc)


if __name__ == "__main__":
    bot.run(config.DISCORD_TOKEN)
