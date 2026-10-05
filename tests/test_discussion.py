import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from loeil import discussion
from loeil.annonces import MemoireAnnonces
from loeil.discussion import Discussion, est_ennui, est_question, formater_remarques, lire_decision


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
    assert texte.index("annonce 2") < texte.index("annonce 1")  # plus récent d'abord
    assert "[n°1 — LE PLUS RÉCENT — publié le 03/10/2026 à 00h00 par Armand]" in texte


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


def _client_espion(appels):
    async def create(**params):
        appels.append(params)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text='{"repondre": false, "reponse": ""}')])

    return SimpleNamespace(messages=SimpleNamespace(create=create), beta=SimpleNamespace(
        messages=SimpleNamespace(create=create)))


def test_appel_ia_opus_par_defaut_avec_repli_et_effort_bas():
    appels = []
    d = Discussion({"annonces": MemoireAnnonces()}, client=_client_espion(appels))
    assert asyncio.run(d._appeler_ia("<conversation></conversation>", "consigne")) is not None
    assert appels[0]["model"] == "claude-opus-5-5"
    assert appels[0]["output_config"]["effort"] == "low"
    assert appels[0]["fallbacks"] == "default"
    assert appels[0]["system"][0]["cache_control"]["ttl"] == "1h"


def test_appel_ia_haiku_sans_effort(monkeypatch):
    monkeypatch.setattr(discussion.config, "CHAT_MODEL", "claude-haiku-4-5")
    appels = []
    d = Discussion({"annonces": MemoireAnnonces()}, client=_client_espion(appels))
    asyncio.run(d._appeler_ia("<conversation></conversation>", "consigne"))
    assert appels[0]["model"] == "claude-haiku-4-5"
    assert "effort" not in appels[0]["output_config"] and "fallbacks" not in appels[0]


def test_plusieurs_sources_dans_le_prompt():
    annonces, bilans = MemoireAnnonces(), MemoireAnnonces(taille=10, max_caracteres=10)
    annonces.ajouter(datetime(2026, 10, 1), "Armand", "Réunion samedi")
    bilans.ajouter(datetime(2026, 9, 28), "Diego", "Bilan très long qui sera coupé")
    texte = Discussion({"annonces": annonces, "bilans_reunions": bilans}, client=object()).texte_sources()
    assert "<annonces>" in texte and "Réunion samedi" in texte
    assert "<bilans_reunions>" in texte and "Bilan trè" in texte and "coupé" not in texte


def test_detection_ennui():
    assert est_ennui("de toute façon y'a rien à faire je me co pour rien")
    assert est_ennui("Je m’ennuie grave")
    assert not est_ennui("on a fait le braquage hier")


def test_remarques_triees_et_limitees():
    msgs = [(datetime(2026, 10, 1, 20), "Fluxy", "je fais les commandes solo tous les soirs"),
            (datetime(2026, 9, 30, 18), "Sienna", "Fluxy gère presque seul l'orga")]
    texte = formater_remarques(msgs)
    assert texte.index("Sienna") < texte.index("Fluxy :")
    assert "[01/10 20h] Fluxy" in texte
    many = [(datetime(2026, 9, 1) + discussion.timedelta(minutes=i), "a", str(i)) for i in range(200)]
    assert formater_remarques(many).count("\n") == discussion.MAX_REMARQUES + 1
    assert "(aucune)" in formater_remarques([])


def test_anti_boucle_et_reaction_silencieuse():
    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    for t in range(discussion.MAX_REPONSES_MEMBRE):
        assert not d.trop_de_reponses(1, 100.0 + t)
        d._reponses_membre.setdefault(1, []).append(100.0 + t)
    assert d.trop_de_reponses(1, 110.0)
    assert not d.trop_de_reponses(1, 100.0 + discussion.FENETRE_REPONSES_SECONDES + 10)

    message = SimpleNamespace(add_reaction=AsyncMock())
    asyncio.run(d._reagir_en_silence(message))
    message.add_reaction.assert_awaited_once_with("👁️")


def test_lire_mute():
    from loeil.discussion import lire_mute
    assert lire_mute('{"repondre": true, "reponse": "Fait.", "mute": " BlackSky16 "}') == "BlackSky16"
    assert lire_mute('{"repondre": true, "reponse": "x", "mute": ""}') == ""


def _membre(nom, staff=False):
    m = discord.Member.__new__(discord.Member)
    return SimpleNamespace(display_name=nom, bot=False, guild_permissions=discord.Permissions(moderate_members=staff),
                           timeout=AsyncMock())


def test_mute_demande_par_staff(monkeypatch):
    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    troll = _membre("BlackSky16")
    monkeypatch.setattr(discussion.discord, "Member", SimpleNamespace)  # les faux membres passent isinstance
    historique = [SimpleNamespace(author=troll)]
    message = SimpleNamespace(mentions=[], author=SimpleNamespace(display_name="Rosita"))
    assert asyncio.run(d._mute_demande_par_staff(message, historique, "blacksky16")) is None
    troll.timeout.assert_awaited_once()
    assert "Je ne vois pas" in asyncio.run(d._mute_demande_par_staff(message, historique, "Inconnu"))
    chef = _membre("Armand", staff=True)
    assert asyncio.run(d._mute_demande_par_staff(message, [SimpleNamespace(author=chef)], "Armand")) == \
        "Je ne mute pas le staff."


def test_demute_demande_par_staff(monkeypatch):
    from loeil.discussion import lire_mute
    assert lire_mute('{"mute": "", "demute": "BlackSky16"}', "demute") == "BlackSky16"
    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    puni = _membre("BlackSky16")
    monkeypatch.setattr(discussion.discord, "Member", SimpleNamespace)
    message = SimpleNamespace(mentions=[], author=SimpleNamespace(display_name="Armand"),
                              guild=SimpleNamespace(get_member_named=lambda n: puni if n == "BlackSky16" else None))
    assert asyncio.run(d._mute_demande_par_staff(message, [], "BlackSky16", lever=True)) is None
    puni.timeout.assert_awaited_once()
    assert puni.timeout.call_args.args[0] is None


def test_lire_refus():
    from loeil.discussion import lire_refus
    assert lire_refus('{"refus_confirme": true}') is True
    assert lire_refus('{"refus_confirme": false}') is False
    assert lire_refus('{}') is False


def test_bilan_en_plusieurs_messages_fusionne():
    from datetime import timedelta
    m = MemoireAnnonces(taille=5, max_caracteres=100)
    debut = datetime(2026, 9, 28, 15, 46)
    m.ajouter(debut, "Fluxy", "Résumé réunion Maldi")
    m.ajouter(debut + timedelta(minutes=1), "Fluxy", "Concernant la drogue")
    m.ajouter(debut + timedelta(hours=2), "Fluxy", "Autre bilan")
    m.ajouter(debut + timedelta(hours=2, minutes=1), "Diego", "Bilan de Diego")
    assert [a.contenu for a in m.annonces] == ["Résumé réunion Maldi\nConcernant la drogue", "Autre bilan",
                                               "Bilan de Diego"]


def test_insulte_envers_l_oeil_mute_direct(monkeypatch):
    from loeil.discussion import lire_insulte
    assert lire_insulte('{"insulte_oeil": true}') is True
    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    monkeypatch.setattr(discussion.discord, "Member", SimpleNamespace)
    insulteur = SimpleNamespace(display_name="Fluxy", mention="<@7>", guild_permissions=discord.Permissions(),
                                timeout=AsyncMock())
    message = SimpleNamespace(author=insulteur, reply=AsyncMock(), add_reaction=AsyncMock(), content="ptite lopsa",
                              guild=None, channel=SimpleNamespace(mention="#discu"), jump_url="url")
    asyncio.run(d._sanctionner_insulte(message))
    insulteur.timeout.assert_awaited_once()
    assert "30 minutes de silence" in message.reply.call_args.args[0]

    staff = SimpleNamespace(display_name="Armand", mention="<@8>",
                            guild_permissions=discord.Permissions(manage_guild=True), timeout=AsyncMock())
    message_staff = SimpleNamespace(author=staff, reply=AsyncMock(), add_reaction=AsyncMock())
    asyncio.run(d._sanctionner_insulte(message_staff))
    staff.timeout.assert_not_called()
    message_staff.add_reaction.assert_awaited_once_with("👁️")


def test_le_lead_a_toujours_une_reponse(monkeypatch):
    monkeypatch.setattr(discussion.config, "LEAD_IDS", {1140051323820187789})
    reponses = iter(['{"repondre": false, "reponse": "", "mute": "", "demute": "", "refus_confirme": false, "insulte_oeil": true}',
                     '{"repondre": true, "reponse": "Je t\u0027écoute.", "mute": "", "demute": "", "refus_confirme": false, "insulte_oeil": false}'])
    consignes = []

    async def faux_appel(conversation, consigne):
        consignes.append(consigne)
        return next(reponses)

    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    d._appeler_ia = faux_appel

    async def historique(**_):
        return
        yield

    lead = SimpleNamespace(id=1140051323820187789, display_name="Armand", guild_permissions=discord.Permissions())
    message = SimpleNamespace(author=lead, content="T'inquiète je vais t'apprendre fils", clean_content="x",
                              channel=SimpleNamespace(id=5, history=historique), reply=AsyncMock(),
                              add_reaction=AsyncMock(), guild=None)
    for _ in range(discussion.MAX_REPONSES_MEMBRE + 1):
        d._reponses_membre.setdefault(lead.id, []).append(discussion.time.monotonic())
    asyncio.run(d.repondre(message, SimpleNamespace(id=999), directe=True))
    assert len(consignes) == 2 and "TOUJOURS" in consignes[1]
    message.reply.assert_awaited_once()
    message.add_reaction.assert_not_called()


def test_memoire_retenue_par_le_staff(monkeypatch):
    from loeil.discussion import lire_retenir
    assert lire_retenir('{"retenir": " Kanan est chez les bleus depuis le 04/10 "}') == "Kanan est chez les bleus depuis le 04/10"
    monkeypatch.setattr(discussion.config, "LEAD_IDS", {1})
    reponse_ia = ('{"repondre": true, "reponse": "Noté.", "mute": "", "demute": "", "refus_confirme": false, '
                  '"insulte_oeil": false, "retenir": "Kanan est chez les bleus depuis le 04/10"}')
    vus = []

    async def faux_appel(conversation, consigne):
        vus.append(conversation)
        return reponse_ia

    notes = []

    async def noter(note, auteur):
        notes.append((note, auteur))
        return True

    async def historique(**_):
        return
        yield

    d = Discussion({"annonces": MemoireAnnonces()}, client=object())
    d._appeler_ia, d.noter = faux_appel, noter

    def message(auteur_id):
        auteur = SimpleNamespace(id=auteur_id, display_name="Armand" if auteur_id == 1 else "Kylian",
                                 guild_permissions=discord.Permissions())
        return SimpleNamespace(author=auteur, content="retiens : Kanan chez les bleus", clean_content="x",
                               channel=SimpleNamespace(id=5, history=historique), reply=AsyncMock(),
                               add_reaction=AsyncMock(), guild=None)

    asyncio.run(d.repondre(message(1), SimpleNamespace(id=999), directe=True))
    assert notes == [("Kanan est chez les bleus depuis le 04/10", "Armand")]
    assert "<date_du_jour>" in vus[0]
    asyncio.run(d.repondre(message(2), SimpleNamespace(id=999), directe=True))  # simple membre : rien n'est noté
    assert len(notes) == 1
