import asyncio
from types import SimpleNamespace

from loeil import strategie


def _client(appels, texte="**📌 Affaire Cabra / Bobby** — urgence : haute"):
    async def create(**params):
        appels.append(params)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=texte)])

    return SimpleNamespace(messages=SimpleNamespace(create=create), beta=SimpleNamespace(
        messages=SimpleNamespace(create=create)))


def test_strategie_utilise_les_sources_la_presence_et_reflechit_fort():
    appels = []
    texte = asyncio.run(strategie.generer_strategie(
        _client(appels), "<bilans_reunions>Cabra ont menacé Bobby</bilans_reunions>",
        "<presence_du_soir>Présents : Rosita</presence_du_soir>"))
    assert texte.startswith("**📌 Affaire Cabra")
    contenu = appels[0]["messages"][0]["content"]
    assert "Cabra ont menacé Bobby" in contenu and "Présents : Rosita" in contenu
    assert "tous les points" in contenu
    assert appels[0]["output_config"]["effort"] == "high"


def test_strategie_sur_un_sujet():
    appels = []
    asyncio.run(strategie.generer_strategie(_client(appels), "x", "y", sujet="Kanan"))
    assert "« Kanan »" in appels[0]["messages"][0]["content"]


def test_refus_donne_none():
    async def create(**params):
        return SimpleNamespace(stop_reason="refusal", content=[])

    client = SimpleNamespace(messages=SimpleNamespace(create=create), beta=SimpleNamespace(
        messages=SimpleNamespace(create=create)))
    assert asyncio.run(strategie.generer_strategie(client, "x", "y")) is None
