import asyncio
import json
from types import SimpleNamespace

from loeil.analyseur import Analyseur, formater_conversation, lire_verdict
from loeil.tension import Message


def test_lire_verdict():
    v = lire_verdict(json.dumps({"niveau": 2, "raison": "r", "message_apaisement": " calme \n",
                                 "personnes": ["A", "B"]}))
    assert v.niveau == 2 and v.message_apaisement == "calme" and v.personnes == ["A", "B"]


def test_conversation_balisee():
    texte = formater_conversation([Message("Fluxy", "salut", "")])
    assert texte == "<conversation>\nFluxy : salut\n</conversation>"


class FauxClient:
    def __init__(self, reponse):
        self.appels = []
        reponse_ = reponse

        async def create(**params):
            self.appels.append(params)
            return reponse_

        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


def _reponse(texte, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=texte)])


def test_analyse_opus_avec_repli_et_effort():
    client = FauxClient(_reponse(json.dumps({"niveau": 3, "raison": "menaces",
                                             "message_apaisement": "on respire", "personnes": []})))
    v = asyncio.run(Analyseur("claude-opus-5-5", client).analyser([Message("a", "b", "")]))
    assert v.niveau == 3
    appel = client.appels[0]
    assert appel["fallbacks"] == "default"
    assert appel["output_config"]["effort"] == "low"


def test_analyse_haiku_sans_effort_ni_repli():
    client = FauxClient(_reponse(json.dumps({"niveau": 0, "raison": "", "message_apaisement": "", "personnes": []})))
    asyncio.run(Analyseur("claude-haiku-4-5", client).analyser([Message("a", "b", "")]))
    appel = client.appels[0]
    assert "fallbacks" not in appel and "effort" not in appel["output_config"]


def test_refus_donne_none():
    client = FauxClient(_reponse("", stop="refusal"))
    assert asyncio.run(Analyseur("claude-opus-5-5", client).analyser([Message("a", "b", "")])) is None
