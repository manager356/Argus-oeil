import logging
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks

from loeil import apaisement, config, missions
from loeil.annonces import MemoireAnnonces
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
# Salons d'infos que L'Œil lit pour répondre : id du salon -> (nom de la partie, mémoire)
_salons_infos: dict[int, tuple[str, MemoireAnnonces]] = {}
if config.ANNONCES_CHANNEL_ID:
    _salons_infos[config.ANNONCES_CHANNEL_ID] = ("annonces", MemoireAnnonces(taille=30, max_caracteres=1500))
if config.BILANS_CHANNEL_ID:
    _salons_infos[config.BILANS_CHANNEL_ID] = ("bilans_reunions", MemoireAnnonces(taille=10, max_caracteres=4000))
if config.OBJECTIFS_CHANNEL_ID:
    _salons_infos[config.OBJECTIFS_CHANNEL_ID] = ("objectifs", MemoireAnnonces(taille=20, max_caracteres=3000))
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
            rapport_missions.start()
            log.info("Missions : présents envoyés à %s, rapport à %s", config.MISSIONS_HOUR, config.RAPPORT_HOUR)
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


@tasks.loop(time=_heure(config.MISSIONS_HOUR))
async def envoi_presents() -> None:
    log.info(await envoyer_presents_aux_chefs(config.MISSIONS_CHEF_IDS))


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
    if message.guild is None or message.author == bot.user:
        return
    # Les annonces sont parfois postées par des bots : on les lit quand même.
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
