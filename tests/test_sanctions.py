import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from loeil import sanctions
from loeil.analyseur import formater_conversation, lire_verdict
from loeil.sanctions import AVERTIR, MUTER, RegistreAvertissements, ids_des_pseudos
from loeil.tension import Message


def test_avertissement_puis_mute_puis_reset():
    r = RegistreAvertissements(duree_secondes=3600)
    assert r.decision(1, 0) == AVERTIR
    assert r.decision(1, 100) == MUTER
    assert r.decision(1, 200) == AVERTIR  # après un mute on repart de zéro


def test_avertissement_expire():
    r = RegistreAvertissements(duree_secondes=3600)
    assert r.decision(1, 0) == AVERTIR
    assert r.decision(1, 3601) == AVERTIR


def test_ids_des_pseudos():
    msgs = [Message("Romano", "x", "", 11), Message("Mr.Fluxy", "y", "", 22), Message("romano", "z", "", 11)]
    assert ids_des_pseudos(["romano ", "Inconnu"], msgs) == [11]
    assert ids_des_pseudos([], msgs) == []


def test_conversation_marque_les_nouveaux_messages():
    msgs = [Message("a", "1", ""), Message("b", "2", ""), Message("c", "3", "")]
    texte = formater_conversation(msgs, 1)
    assert texte.index("b : 2") < texte.index("--- nouveaux messages ---") < texte.index("c : 3")


def test_verdict_sans_champ_irrespectueux_reste_lisible():
    v = lire_verdict('{"niveau": 1, "raison": "r", "message_apaisement": "", "personnes": []}')
    assert v.irrespectueux == []


def _membre(staff=False):
    perms = discord.Permissions(moderate_members=staff)
    return SimpleNamespace(id=5, display_name="Romano", mention="<@5>", guild_permissions=perms,
                           timeout=AsyncMock())


def _salon(membre):
    guild = SimpleNamespace(get_member=lambda i: membre, fetch_member=AsyncMock())
    return SimpleNamespace(guild=guild, send=AsyncMock())


def test_appliquer_avertit_puis_mute():
    membre = _membre()
    salon = _salon(membre)
    r = RegistreAvertissements(3600)
    assert asyncio.run(sanctions.appliquer(r, salon, 5, 0, "insulte"))[0] == AVERTIR
    membre.timeout.assert_not_called()
    assert asyncio.run(sanctions.appliquer(r, salon, 5, 10, "insulte"))[0] == MUTER
    membre.timeout.assert_awaited_once()
    assert "30 minutes" in salon.send.call_args.args[0]


def test_staff_jamais_sanctionne():
    membre = _membre(staff=True)
    salon = _salon(membre)
    assert asyncio.run(sanctions.appliquer(RegistreAvertissements(3600), salon, 5, 0, "x")) is None
    salon.send.assert_not_called()
