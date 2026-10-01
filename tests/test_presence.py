from datetime import date

from loeil.presence import (StockageVotes, appliquer_vote, construire_embed, lire_votes_embed, texte_champ,
                      titre_du_jour, votes_vides)


def test_titre_en_francais():
    assert titre_du_jour(date(2026, 10, 1)) == "📋 Présence du jeudi 1 octobre"


def test_vote_change_et_retire():
    v = appliquer_vote(votes_vides(), 1, "present")
    assert v["present"] == [1]
    v = appliquer_vote(v, 1, "absent")
    assert v["present"] == [] and v["absent"] == [1]
    v = appliquer_vote(v, 1, "absent")  # reclic = retrait
    assert v == votes_vides()


def test_embed_compte_les_votes():
    v = appliquer_vote(appliquer_vote(votes_vides(), 1, "present"), 2, "present")
    embed = construire_embed("titre", v)
    assert embed.fields[0].name == "✅ Présents (2)"
    assert embed.fields[0].value == "<@1>\n<@2>"
    assert embed.fields[1].value == "—"


def test_champ_trop_long_tronque():
    texte = texte_champ(list(range(10**17, 10**17 + 100)))
    assert len(texte) <= 1024
    assert "autre(s)" in texte


def test_stockage_persiste(tmp_path):
    chemin = tmp_path / "presence.json"
    s = StockageVotes(chemin)
    s.creer(42, "titre")
    s.obtenir(42)["votes"]["present"].append(7)
    s.sauver()
    assert StockageVotes(chemin).obtenir(42)["votes"]["present"] == [7]


def test_votes_relus_depuis_embed():
    v = appliquer_vote(appliquer_vote(votes_vides(), 1, "present"), 2, "peutetre")
    assert lire_votes_embed(construire_embed("t", v)) == v
