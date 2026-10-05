import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from loeil import faits_armes
from loeil.faits_armes import Extrait, cite, formater_extraits


def test_cite_nom_complet_ou_un_mot():
    assert cite("Kanan, lieutenant de l'Argus, a kidnappé 16", "Kanan")
    assert cite("Diego récupère l'emplacement des percuteurs", "Diego Veiga / Ghost")
    assert cite("Mission donnée à Rosita", "bobigny/rosita")
    assert not cite("Les Cabra ont menacé Bobby", "Kanan")
    assert not cite("on a vu un mec", "Al")  # mots trop courts ignorés


def test_extraits_classes_du_plus_ancien_au_plus_recent():
    e1 = Extrait(datetime(2026, 10, 4, 22, tzinfo=timezone.utc), "Bilan", "L'oeil", "Kanan arrêté")
    e2 = Extrait(datetime(2026, 9, 28, 20, tzinfo=timezone.utc), "Mémoire", "L'oeil", "Kanan promu")
    texte = formater_extraits([e1, e2])
    assert texte.index("Kanan promu") < texte.index("Kanan arrêté")
    assert "[Bilan — 05/10/2026 — L'oeil]" in texte  # heure de Paris
    assert formater_extraits([]) == "(aucune archive ne le cite)"


def test_rediger_transmet_archives_et_missions():
    appels = []

    async def create(**params):
        appels.append(params)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text="**⚔️ Faits d'armes — Kanan**")])

    client = SimpleNamespace(messages=SimpleNamespace(create=create), beta=SimpleNamespace(
        messages=SimpleNamespace(create=create)))
    texte = asyncio.run(faits_armes.rediger(client, "Kanan", "[Bilan] Kanan a kidnappé 16",
                                            "- 05/10 — Kanan : percuteurs → accomplie"))
    assert texte.startswith("**⚔️")
    contenu = appels[0]["messages"][0]["content"]
    assert "<membre>Kanan</membre>" in contenu and "kidnappé 16" in contenu and "percuteurs" in contenu
