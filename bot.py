import logging
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks

from loeil import apaisement, config
from loeil.annonces import MemoireAnnonces
from loeil.discussion import Discussion
from loeil.presence import StockageVotes, VuePresence, publier_sondage


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("loeil.bot")

FUSEAU = ZoneInfo("Europe/Paris")
_heure, _minute = (int(x) for x in config.PRESENCE_HOUR.split(":"))
_stockage_presence = StockageVotes(Path(__file__).parent / "donnees" / "presence.json")
# Salons d'infos que L'Œil lit pour répondre : id du salon -> (nom de la partie, mémoire)
_salons_infos: dict[int, tuple[str, MemoireAnnonces]] = {}
if config.ANNONCES_CHANNEL_ID:
    _salons_infos[config.ANNONCES_CHANNEL_ID] = ("annonces", MemoireAnnonces(taille=30, max_caracteres=1500))
if config.BILANS_CHANNEL_ID:
    _salons_infos[config.BILANS_CHANNEL_ID] = ("bilans_reunions", MemoireAnnonces(taille=10, max_caracteres=4000))
_discussion = Discussion({titre: memoire for titre, memoire in _salons_infos.values()})


_intents = discord.Intents.default()
_intents.message_content = True


class LoeilClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=_intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.add_view(VuePresence(_stockage_presence))
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
