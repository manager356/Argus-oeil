import asyncio
from datetime import date
from types import SimpleNamespace

import discord

from loeil import bilan
from loeil.bilan import decouper


def test_decouper_respecte_la_limite_et_les_lignes():
    texte = "\n".join(f"- ligne {i} " + "x" * 50 for i in range(100))
    morceaux = decouper(texte, limite=500)
    assert all(len(m) <= 500 for m in morceaux)
    assert "\n".join(morceaux).replace("\n", "") == texte.replace("\n", "")
    assert all(m.startswith("- ligne") for m in morceaux)  # coupé entre deux lignes


def test_decouper_ligne_trop_longue():
    morceaux = decouper("a" * 1200, limite=500)
    assert [len(m) for m in morceaux] == [500, 500, 200]


def test_texte_court_un_seul_message():
    assert decouper("**Titre**\n- un point") == ["**Titre**\n- un point"]


def test_generer_bilan_appelle_le_modele_avec_les_notes_et_missions():
    appels = []

    async def create(**params):
        appels.append(params)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text="**📜 Bilan**\n- 60K reçus de DK")])

    client = SimpleNamespace(messages=SimpleNamespace(create=create), beta=SimpleNamespace(
        messages=SimpleNamespace(create=create)))
    texte = asyncio.run(bilan.generer_bilan(client, date(2026, 10, 5), "Armand", "Maldi",
                                            "DK a donné 60k pour les tops", "- Rosita : percuteurs → accomplie"))
    assert texte.startswith("**📜 Bilan**")
    contenu = appels[0]["messages"][0]["content"]
    assert "DK a donné 60k" in contenu and "Rosita : percuteurs" in contenu and "05/10/2026" in contenu


def test_bilan_reserve_au_staff_et_leads(monkeypatch):
    monkeypatch.setattr(bilan.config, "LEAD_IDS", {1})
    assert bilan.peut_faire_un_bilan(SimpleNamespace(id=1))
    assert not bilan.peut_faire_un_bilan(SimpleNamespace(id=2))


def test_le_formulaire_se_construit():
    async def scenario():
        modal = bilan.ModalBilan(object(), date(2026, 10, 5), None)
        assert len(modal.children) == 3

    asyncio.run(scenario())
