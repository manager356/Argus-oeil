from loeil.tension import MOTS_DECLENCHEURS, EtatSalon, Message, compiler_declencheurs, est_suspect

MOTIF = compiler_declencheurs(MOTS_DECLENCHEURS)


def test_messages_tendus_detectes():
    assert est_suspect("bouger vos cul d’enculer", MOTIF)
    assert est_suspect("Celui qui est pas content venez je vous bz", MOTIF)
    assert est_suspect("t'es un vrai trou de balle", MOTIF)
    assert est_suspect("C'EST TJR LES MEMES QUI FONT TOUT ICI", MOTIF)
    assert est_suspect("Bâtard va", MOTIF)


def test_messages_normaux_ignores():
    assert not est_suspect("Reel je fais une annonce demain tqt", MOTIF)
    assert not est_suspect("On fait une dispute RP ce soir ?", MOTIF)  # "pute" dans "dispute"
    assert not est_suspect("le contrat d'intérim est réputé facile", MOTIF)
    assert not est_suspect("je vais au bar en ville", MOTIF)
    assert not est_suspect("OK", MOTIF)


def test_mots_courts_doivent_etre_entiers():
    assert est_suspect("tg", MOTIF)
    assert not est_suspect("tgv demain", MOTIF)
    assert not est_suspect("banane", MOTIF)


def test_etat_salon_pause_apres_intervention():
    etat = EtatSalon(3)
    etat.ajouter(Message("a", "salut", ""), suspect=False)
    assert not etat.doit_analyser(100, 1800)
    etat.ajouter(Message("b", "ntm", ""), suspect=True)
    assert etat.doit_analyser(100, 1800)
    etat.marquer_analyse()
    etat.marquer_intervention(100)
    etat.ajouter(Message("b", "ntm encore", ""), suspect=True)
    assert not etat.doit_analyser(200, 1800)
    assert etat.doit_analyser(100 + 1801, 1800)


def test_historique_limite():
    etat = EtatSalon(2)
    for i in range(5):
        etat.ajouter(Message("a", str(i), ""), suspect=False)
    assert [m.contenu for m in etat.historique] == ["3", "4"]
