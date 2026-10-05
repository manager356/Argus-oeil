import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from loeil import reglages
from loeil.reglages import embed_reglages, heure_valide, lire_reglages


def test_heures_acceptees():
    assert heure_valide("18h") == "18:00"
    assert heure_valide("18:30") == "18:30"
    assert heure_valide(" 9h05 ") == "09:05"
    assert heure_valide("21H") == "21:00"
    assert heure_valide("25h") is None
    assert heure_valide("18:75") is None
    assert heure_valide("demain") is None


def test_reglages_aller_retour():
    valeurs = {"heure_sondage": "18:30"}
    assert lire_reglages(embed_reglages(valeurs)) == valeurs


def test_definir_cree_puis_edite_le_message():
    r = reglages.Reglages()
    message = SimpleNamespace(edit=AsyncMock())
    salon = SimpleNamespace(send=AsyncMock(return_value=message))
    asyncio.run(r.definir(salon, "heure_sondage", "18:00"))
    salon.send.assert_awaited_once()
    asyncio.run(r.definir(salon, "heure_sondage", "19:00"))
    message.edit.assert_awaited_once()
    assert r.valeurs == {"heure_sondage": "19:00"}
