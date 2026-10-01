"""Détection de tension : pré-filtre gratuit (mots-clés, majuscules) et suivi par salon.

Le pré-filtre évite d'appeler l'IA sur chaque message : on ne lance une analyse
que lorsqu'un message "suspect" apparaît dans un salon surveillé.
"""
import re
import unicodedata
from collections import deque
from dataclasses import dataclass

# Mots qui déclenchent une analyse IA. Un mot attrape aussi ses variantes
# ("encul" -> "enculer", "enculé"). Les mots de 3 lettres ou moins doivent être entiers.
MOTS_DECLENCHEURS = [
    "encul", "ntm", "nique", "fdp", "pute", "connard", "connasse", "batard",
    "ta gueule", "ferme ta", "ferme la", "trou de balle", "zgeg", "bz", "je vais te",
    "caner", "ban", "quitter le serveur", "va te faire", "fils de", "abruti", "debile",
    "mongol", "clochard", "salope", "pd", "tg", "casse les couilles",
    "rien a branler", "je m'en bats", "degage",
    "ta race", "sale merde", "sale con", "merde", "tue", "creve", "on se regle", "viens on se",
    "t'es le probleme", "c'est toi le probleme", "es toi le probleme",
]


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, apostrophes unifiées."""
    texte = texte.replace("’", "'").lower()
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c))


def compiler_declencheurs(mots: list[str]) -> re.Pattern:
    """Chaque mot doit commencer un mot du message ("encul" attrape "enculer").
    Les mots très courts (<= 3 lettres, ex. "tg", "fdp") doivent être un mot entier."""
    morceaux = []
    for mot in mots:
        m = normaliser(mot).strip()
        if not m:
            continue
        motif = r"(?<!\w)" + re.escape(m)
        if len(m) <= 3:
            motif += r"(?!\w)"
        morceaux.append(motif)
    if not morceaux:
        return re.compile(r"(?!x)x")  # ne correspond à rien
    return re.compile("|".join(morceaux))


def est_suspect(texte: str, declencheurs: re.Pattern) -> bool:
    """Vrai si le message contient un mot déclencheur ou est écrit en majuscules."""
    if declencheurs.search(normaliser(texte)):
        return True
    lettres = [c for c in texte if c.isalpha()]
    if len(lettres) >= 15 and sum(c.isupper() for c in lettres) / len(lettres) > 0.7:
        return True
    return False


@dataclass
class Message:
    auteur: str
    contenu: str
    lien: str
    auteur_id: int = 0


class EtatSalon:
    """Historique récent d'un salon et état de la surveillance."""

    def __init__(self, taille_historique: int):
        self.historique: deque[Message] = deque(maxlen=taille_historique)
        self.suspect = False
        self.derniere_intervention: float | None = None
        self.nb_nouveaux = 0  # messages arrivés depuis la dernière analyse

    def ajouter(self, message: Message, suspect: bool) -> None:
        self.historique.append(message)
        self.nb_nouveaux = min(self.nb_nouveaux + 1, len(self.historique))
        if suspect:
            self.suspect = True

    def nouveaux(self) -> list[Message]:
        return list(self.historique)[len(self.historique) - self.nb_nouveaux:]

    def en_pause(self, maintenant: float, pause_secondes: float) -> bool:
        return (
            self.derniere_intervention is not None
            and maintenant - self.derniere_intervention < pause_secondes
        )

    def doit_analyser(self) -> bool:
        # On analyse même pendant la pause : les avertissements/mutes restent actifs,
        # seule la pause empêche de reposter un message d'apaisement.
        return self.suspect

    def marquer_analyse(self) -> None:
        self.suspect = False
        self.nb_nouveaux = 0

    def marquer_intervention(self, maintenant: float) -> None:
        self.derniere_intervention = maintenant
