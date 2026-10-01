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


def test_annonce_des_missions():
    embed = missions.embed_annonce_missions(date(2026, 10, 1), [(1, "percuteurs Lopez"), (2, "voir les Devils")], "Armand")
    assert embed.title == "🎯 Missions du soir — 01/10"
    assert embed.description == "<@1> — percuteurs Lopez\n<@2> — voir les Devils"


def test_annoncer_missions_poste_et_pingue(monkeypatch):
    salon = SimpleNamespace(send=AsyncMock())
    client = SimpleNamespace(get_channel=lambda i: salon)
    monkeypatch.setattr(missions.config, "ANNONCES_CHANNEL_ID", 42)
    assert asyncio.run(missions.annoncer_missions(client, date(2026, 10, 1), {1: "a", 2: "b"}, "Armand"))
    assert salon.send.call_args.kwargs["content"] == "<@1> <@2>"
    assert not asyncio.run(missions.annoncer_missions(client, date(2026, 10, 1), {}, "Armand"))


def test_mentions_remplacees_par_les_pseudos():
    from loeil.annonces import remplacer_mentions
    guild = SimpleNamespace(get_member=lambda i: SimpleNamespace(display_name="Rosita") if i == 1 else None)
    assert remplacer_mentions("<@1> — percuteurs, <@!9> — x", guild) == "@Rosita — percuteurs, <@!9> — x"


def test_relance_seulement_les_missions_en_cours(tmp_path):
    s = StockageMissions(tmp_path / "m.json")
    jour = date(2026, 10, 1)
    s.ajouter(jour, 1, "Rosita", "percuteurs", "Armand")
    s.ajouter(jour, 2, "Diego", "Devils", "Armand")
    s.ajouter(jour, 3, "Fluxy", "prison", "Armand")
    s.statuer(jour, 2, ACCOMPLIE)
    assert [m for m, _ in missions.a_relancer(s.soiree(jour))] == [1, 3]

    ok_user = SimpleNamespace(send=AsyncMock())
    ferme = SimpleNamespace(send=AsyncMock(side_effect=missions.discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "MP fermés")))
    client = SimpleNamespace(get_user=lambda i: ok_user if i == 1 else ferme, fetch_user=AsyncMock())

    async def scenario():
        missions.VueMission(s)  # la vue doit pouvoir se construire dans la boucle
        return await missions.relancer(client, s, jour)

    relances, echecs = asyncio.run(scenario())
    assert relances == ["Rosita"] and echecs == ["Fluxy"]
    assert "Rappel" in ok_user.send.call_args.kwargs["embed"].title


def test_date_du_rapport_a_minuit():
    assert date_soiree(datetime(2026, 10, 2, 0, 0, tzinfo=PARIS)) == date(2026, 10, 1)


def test_refus_compte_a_part_dans_le_rapport(tmp_path):
    s = StockageMissions(tmp_path / "m.json")
    jour = date(2026, 10, 1)
    s.ajouter(jour, 1, "BlackSky16", "percuteurs", "Armand")
    s.ajouter(jour, 2, "Rosita", "Devils", "Armand")
    s.statuer(jour, 1, missions.REFUS)
    soiree = s.soiree(jour)
    ok, ko, attente, _ = lignes_rapport(soiree, {})
    assert attente == ["**Rosita** — Devils"]
    assert missions.lignes_refus(soiree) == ["**BlackSky16** — percuteurs"]
    noms = [f.name for f in embed_rapport(jour, soiree, {}).fields]
    assert "🚫 Refus d'ordre (1)" in noms
    assert [m for m, _ in missions.a_relancer(soiree)] == [2]  # pas de relance pour un refus
