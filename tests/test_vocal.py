import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from loeil import discussion, vocal
from loeil.annonces import MemoireAnnonces
from loeil.discussion import Discussion, lire_vocal


def test_lire_vocal():
    assert lire_vocal('{"vocal": "dire", "texte_vocal": " On se retrouve à 21h. ", "cible_vocal": ""}') == \
        ("dire", "On se retrouve à 21h.", "")
    assert lire_vocal('{"vocal": "n_importe_quoi"}')[0] == "aucune"
    assert lire_vocal("{}") == ("aucune", "", "")


def test_salon_vocal_de_l_auteur_sinon_par_defaut(monkeypatch):
    salon_auteur = discord.VoiceChannel.__new__(discord.VoiceChannel)
    auteur = SimpleNamespace(voice=SimpleNamespace(channel=salon_auteur))
    assert vocal.salon_vocal_de(auteur, None) is salon_auteur
    salon_defaut = discord.VoiceChannel.__new__(discord.VoiceChannel)
    monkeypatch.setattr(vocal.config, "VOCAL_CHANNEL_ID", 7)
    guild = SimpleNamespace(get_channel=lambda i: salon_defaut if i == 7 else None)
    assert vocal.salon_vocal_de(SimpleNamespace(voice=None), guild) is salon_defaut
    monkeypatch.setattr(vocal.config, "VOCAL_CHANNEL_ID", None)
    assert vocal.salon_vocal_de(SimpleNamespace(voice=None), guild) is None


def test_ordre_vocal_sans_vocal_demande_de_rejoindre():
    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    message = SimpleNamespace(guild=SimpleNamespace(get_channel=lambda i: None),
                              author=SimpleNamespace(voice=None, display_name="Armand"), mentions=[])
    texte = asyncio.run(d._executer_vocal(message, [], "rejoindre", "", ""))
    assert "Rejoins un salon vocal" in texte


def test_mute_vocal_sur_ordre(monkeypatch):
    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    monkeypatch.setattr(discussion.discord, "Member", SimpleNamespace)
    cible = SimpleNamespace(display_name="BlackSky16", bot=False, guild_permissions=discord.Permissions(),
                            edit=AsyncMock())
    message = SimpleNamespace(guild=SimpleNamespace(get_member_named=lambda n: None), mentions=[],
                              author=SimpleNamespace(display_name="Armand"))
    historique = [SimpleNamespace(author=cible)]
    assert asyncio.run(d._executer_vocal(message, historique, "mute_vocal", "", "BlackSky16")) is None
    assert cible.edit.call_args.kwargs["mute"] is True
    assert asyncio.run(d._executer_vocal(message, historique, "demute_vocal", "", "BlackSky16")) is None
    assert cible.edit.call_args.kwargs["mute"] is False


def test_synthese_vocale_produit_un_mp3(tmp_path):
    chemin = str(tmp_path / "voix.mp3")
    try:
        asyncio.run(vocal.synthetiser("Je suis L'Œil.", chemin))
    except Exception:  # pas de réseau : le test ne s'applique pas
        return
    assert os.path.getsize(chemin) > 1000
