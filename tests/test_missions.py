import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from loeil import missions
from loeil.missions import (ACCOMPLIE, RATEE, StockageMissions, associer_missions, date_soiree,
                            embed_mission, embed_rapport, lignes_rapport, texte_modele)

PARIS = ZoneInfo("Europe/Paris")
MEMBRES = {1: "Romano Dalarmand", 2: "Mr.Fluxy", 3: "Sienna / Skye"}


def test_date_soiree_deborde_apres_minuit():
    assert date_soiree(datetime(2026, 10, 1, 20, 0, tzinfo=PARIS)) == date(2026, 10, 1)
    assert date_soiree(datetime(2026, 10, 2, 1, 30, tzinfo=PARIS)) == date(2026, 10, 1)
    assert date_soiree(datetime(2026, 10, 2, 13, 0, tzinfo=PARIS)) == date(2026, 10, 2)


def test_associer_missions():
    texte = texte_modele(list(MEMBRES.values()))
    texte = texte.replace("Romano Dalarmand : ", "Romano Dalarmand : farmer les ressources")
    texte = texte.replace("Mr.Fluxy : ", "@mr.fluxy : gérer les commandes : 3 caisses")
    texte += "\nInconnu : truc\nligne sans deux points"
    attributions, inconnues = associer_missions(texte, MEMBRES)
    assert attributions == {1: "farmer les ressources", 2: "gérer les commandes : 3 caisses"}
    assert inconnues == ["Inconnu : truc", "ligne sans deux points"]


def test_associer_par_debut_de_pseudo_si_unique():
    attributions, _ = associer_missions("romano : contacts Cabra\nsienna : armurerie", MEMBRES)
    assert attributions == {1: "contacts Cabra", 3: "armurerie"}


def test_stockage_et_rapport(tmp_path):
    s = StockageMissions(tmp_path / "m.json")
    jour = date(2026, 10, 1)
    s.ajouter(jour, 1, "Romano", "ressources", "Armand")
    s.ajouter(jour, 2, "Fluxy", "commandes", "Armand")
    s.ajouter(jour, 3, "Sienna", "armurerie", "Armand")
    s.statuer(jour, 1, ACCOMPLIE)
    s.statuer(jour, 2, RATEE, "pas assez de monde")
    relu = StockageMissions(tmp_path / "m.json").soiree(jour)
    ok, ko, attente, sans = lignes_rapport(relu, {1: "Romano", 2: "Fluxy", 3: "Sienna", 4: "Kylian"})
    assert ok == ["**Romano** — ressources"]
    assert ko == ["**Fluxy** — commandes _(pas assez de monde)_"]
    assert attente == ["**Sienna** — armurerie"]
    assert sans == ["Kylian"]
    assert embed_rapport(jour, relu, {}).fields[0].name == "✅ Accomplies (1)"


def test_jour_relu_depuis_embed_de_mission():
    embed = embed_mission(date(2026, 10, 1), "ressources", "Armand")
    assert missions._jour_depuis_embed(embed) == date(2026, 10, 1)
    assert missions._infos_depuis_embed(embed) == ("ressources", "Armand")


def test_envoyer_mission_enregistre_seulement_si_mp_ok(tmp_path):
    s = StockageMissions(tmp_path / "m.json")
    utilisateur = SimpleNamespace(send=AsyncMock())
    client = SimpleNamespace(get_user=lambda i: utilisateur, fetch_user=AsyncMock())

    async def scenario():
        return await missions.envoyer_mission(client, s, date(2026, 10, 1), 1, "Romano", "ressources", "Armand")

    assert asyncio.run(scenario()) is True
    utilisateur.send.assert_awaited_once()
    assert s.soiree(date(2026, 10, 1))["1"]["mission"] == "ressources"


def test_les_vues_se_construisent(tmp_path):
    async def scenario():
        s = StockageMissions(tmp_path / "m.json")
        vue = missions.VueAttribution(object(), s, AsyncMock())
        assert [i.custom_id for i in vue.children] == ["missions:attribuer"]
        assert [i.custom_id for i in missions.VueMission(s).children] == ["mission:ok", "mission:ko"]

    asyncio.run(scenario())
