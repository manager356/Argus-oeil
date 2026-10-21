"""L'Œil en vocal : il rejoint un salon vocal, parle (synthèse vocale), mute / démute sur ordre."""
import asyncio
import logging
import os
import shutil
import tempfile

import aiohttp
import discord
import edge_tts

from loeil import config

log = logging.getLogger("loeil.vocal")

ACTIONS = ("aucune", "rejoindre", "dire", "quitter", "mute_vocal", "demute_vocal")
MAX_CARACTERES_PAROLE = 1200  # au-delà, c'est trop long à écouter


URL_ELEVENLABS = "https://api.elevenlabs.io/v1/text-to-speech/{voix}?output_format=mp3_44100_128"


async def synthetiser_elevenlabs(texte: str, chemin: str) -> None:
    """Voix ElevenLabs (payante, très réaliste). Lève une exception en cas d'échec."""
    corps = {
        "text": texte[:MAX_CARACTERES_PAROLE],
        "model_id": config.ELEVENLABS_MODEL,
        # Voix posée et grave : un peu de stabilité, un soupçon de style, débit légèrement lent.
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.25, "speed": 0.95},
    }
    entetes = {"xi-api-key": config.ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    delai = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=delai) as session:
        async with session.post(URL_ELEVENLABS.format(voix=config.ELEVENLABS_VOICE_ID),
                                json=corps, headers=entetes) as reponse:
            if reponse.status != 200:
                detail = (await reponse.text())[:300]
                raise RuntimeError(f"ElevenLabs HTTP {reponse.status} : {detail}")
            audio = await reponse.read()
    with open(chemin, "wb") as fichier:
        fichier.write(audio)


async def synthetiser(texte: str, chemin: str, essais: int = 3) -> None:
    """Écrit le texte lu par la voix de L'Œil dans un fichier mp3.
    ElevenLabs si configuré ; sinon (ou s'il échoue, ex. quota épuisé) la voix gratuite Microsoft."""
    if config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID:
        try:
            await synthetiser_elevenlabs(texte, chemin)
            return
        except Exception as exc:
            log.warning("ElevenLabs indisponible, voix gratuite en secours : %s", exc)
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


def preparer_audio() -> str:
    """Charge Opus (encodage du son pour Discord) et vérifie ffmpeg. Retourne un état lisible pour les logs."""
    if not discord.opus.is_loaded():
        for nom in ("opus", "libopus.so.0", "libopus.so", "libopus-0.dll"):
            try:
                discord.opus.load_opus(nom)
                break
            except OSError:
                continue
    ffmpeg = shutil.which("ffmpeg") is not None
    return f"opus={'ok' if discord.opus.is_loaded() else 'ABSENT'} ffmpeg={'ok' if ffmpeg else 'ABSENT'}"


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
