"""L'Œil en vocal : il rejoint un salon vocal, parle (synthèse vocale), mute / démute sur ordre."""
import asyncio
import logging
import os
import tempfile

import discord
import edge_tts

from loeil import config

log = logging.getLogger("loeil.vocal")

ACTIONS = ("aucune", "rejoindre", "dire", "quitter", "mute_vocal", "demute_vocal")
MAX_CARACTERES_PAROLE = 1200  # au-delà, c'est trop long à écouter


async def synthetiser(texte: str, chemin: str, essais: int = 3) -> None:
    """Écrit le texte lu par la voix de L'Œil dans un fichier mp3 (le service gratuit a parfois des ratés)."""
    for essai in range(1, essais + 1):
        try:
            await edge_tts.Communicate(texte[:MAX_CARACTERES_PAROLE], config.VOIX_OEIL,
                                       rate=config.VOIX_VITESSE, pitch=config.VOIX_HAUTEUR).save(chemin)
            return
        except Exception as exc:
            if essai == essais:
                raise
            log.warning("Synthèse vocale ratée (essai %d) : %s", essai, exc)
            await asyncio.sleep(1.5 * essai)


class Vocal:
    """Une seule connexion vocale à la fois ; les prises de parole passent l'une après l'autre."""

    def __init__(self) -> None:
        self._verrou = asyncio.Lock()

    @staticmethod
    def connexion(guild: discord.Guild) -> discord.VoiceClient | None:
        vc = guild.voice_client
        return vc if isinstance(vc, discord.VoiceClient) and vc.is_connected() else None

    async def rejoindre(self, salon: discord.VoiceChannel) -> discord.VoiceClient:
        vc = self.connexion(salon.guild)
        if vc is None:
            return await salon.connect(self_deaf=True)  # il parle, il n'écoute pas
        if vc.channel != salon:
            await vc.move_to(salon)
        return vc

    async def dire(self, salon: discord.VoiceChannel, texte: str) -> None:
        async with self._verrou:
            vc = await self.rejoindre(salon)
            fd, chemin = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            try:
                await synthetiser(texte, chemin)
                fini = asyncio.Event()
                boucle = asyncio.get_running_loop()
                vc.play(discord.FFmpegPCMAudio(chemin),
                        after=lambda erreur: boucle.call_soon_threadsafe(fini.set))
                await fini.wait()
            finally:
                try:
                    os.remove(chemin)
                except OSError:
                    pass

    async def quitter(self, guild: discord.Guild) -> bool:
        vc = self.connexion(guild)
        if vc is None:
            return False
        await vc.disconnect()
        return True


def salon_vocal_de(auteur: discord.abc.User, guild: discord.Guild | None) -> discord.VoiceChannel | None:
    """Le vocal où se trouve l'auteur, sinon le vocal par défaut (VOCAL_CHANNEL_ID)."""
    etat = getattr(auteur, "voice", None)
    if etat is not None and isinstance(etat.channel, discord.VoiceChannel):
        return etat.channel
    if guild is not None and config.VOCAL_CHANNEL_ID:
        salon = guild.get_channel(config.VOCAL_CHANNEL_ID)
        if isinstance(salon, discord.VoiceChannel):
            return salon
    return None
