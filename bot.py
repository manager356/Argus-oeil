import logging

import discord
from discord import app_commands

from loeil import config, interview


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("loeil.bot")


_intents = discord.Intents.default()
_intents.members = True
_intents.message_content = True
_intents.dm_messages = True


class LoeilClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=_intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        if config.GUILD_ID is not None:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands synchronisées sur le serveur %s", config.GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Slash commands synchronisées globalement (peut prendre jusqu'à 1h)")


bot = LoeilClient()


@bot.tree.command(name="postuler", description="Démarrer un entretien avec L'Œil.")
async def postuler(interaction: discord.Interaction) -> None:
    user = interaction.user
    if interview.is_active(user.id):
        await interaction.response.send_message(
            "Un entretien est déjà en cours. Vérifie tes messages privés.",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        "Vérifie tes messages privés.",
        ephemeral=True,
    )
    guild = interaction.guild
    await interview.start(bot, user, guild)


@bot.event
async def on_ready() -> None:
    log.info("L'Œil est connecté en tant que %s (id=%s)", bot.user, bot.user.id if bot.user else "?")


@bot.event
async def on_member_join(member: discord.Member) -> None:
    if member.bot:
        return
    await interview.start(bot, member, member.guild)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return
    if message.guild is None:
        await interview.handle_response(bot, message.author, message.content)


if __name__ == "__main__":
    bot.run(config.DISCORD_TOKEN)
