import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import discord

from loeil import discussion
from loeil.annonces import MemoireAnnonces
from loeil.discussion import Discussion, est_question, lire_decision


def test_detection_des_questions():
    assert est_question("C'est quand la prochaine réunion ?")
    assert est_question("comment on rejoint l'orga")
    assert est_question("quelqu’un sait si le serveur reboot")
    assert not est_question("salut")
    assert not est_question("je vais au bar en ville ce soir")


def test_lire_decision():
    assert lire_decision(json.dumps({"repondre": True, "reponse": " Samedi 21h. "})) == "Samedi 21h."
    assert lire_decision(json.dumps({"repondre": False, "reponse": "x"})) is None
    assert lire_decision(json.dumps({"repondre": True, "reponse": ""})) is None


def test_memoire_annonces_limitee_et_formatee():
    m = MemoireAnnonces(taille=2)
    for i in range(3):
        m.ajouter(datetime(2026, 10, i + 1), "Armand", f"annonce {i}")
    texte = m.texte()
    assert "annonce 0" not in texte and "annonce 2" in texte
    assert "[03/10/2026 — Armand]" in texte


BOT = SimpleNamespace(id=999)


def _message(contenu, auteur_id=1, salon_id=10, mentions=(), reference=None):
    return SimpleNamespace(
        content=contenu, author=SimpleNamespace(id=auteur_id), channel=SimpleNamespace(id=salon_id),
        mentions=list(mentions), reference=reference,
    )


def test_mention_et_reponse_au_bot_sont_directes():
    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    assert d.doit_considerer(_message("salut", mentions=[BOT]), BOT) == (True, True)
    msg_du_bot = discord.Message.__new__(discord.Message)
    msg_du_bot.author = BOT
    ref = SimpleNamespace(resolved=msg_du_bot)
    assert d.doit_considerer(_message("merci", reference=ref), BOT) == (True, True)


def test_question_spontanee_limitee_par_salon(monkeypatch):
    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    assert d.doit_considerer(_message("c'est quand la réunion ?"), BOT) == (True, False)
    d._derniere_spontanee[10] = discussion.time.monotonic()
    assert d.doit_considerer(_message("c'est quand la réunion ?", auteur_id=2), BOT) == (False, False)
    assert d.doit_considerer(_message("ok"), BOT) == (False, False)


def test_appel_ia_utilise_haiku_sans_effort():
    appels = []

    async def create(**params):
        appels.append(params)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text='{"repondre": false, "reponse": ""}')])

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    d = Discussion({"annonces": MemoireAnnonces()}, client=client)
    assert asyncio.run(d._appeler_ia("<conversation></conversation>", "consigne")) is not None
    assert appels[0]["model"] == "claude-haiku-4-5"
    assert "effort" not in appels[0]["output_config"]


def test_plusieurs_sources_dans_le_prompt():
    annonces, bilans = MemoireAnnonces(), MemoireAnnonces(taille=10, max_caracteres=10)
    annonces.ajouter(datetime(2026, 10, 1), "Armand", "Réunion samedi")
    bilans.ajouter(datetime(2026, 9, 28), "Diego", "Bilan très long qui sera coupé")
    texte = Discussion({"annonces": annonces, "bilans_reunions": bilans}, client=object()).texte_sources()
    assert "<annonces>" in texte and "Réunion samedi" in texte
    assert "<bilans_reunions>" in texte and "Bilan trè" in texte and "coupé" not in texte
