"""Test de la voix ElevenLabs de L'Œil, en local, sans Discord ni Railway.

Lancement (depuis le dossier Argus-oeil) :
    .venv\\Scripts\\python outils\\tester_voix.py

La clé est demandée en saisie masquée : elle n'est ni affichée, ni enregistrée.
Le résultat est écrit dans outils\\voix_test_elevenlabs.mp3, puis ouvert pour l'écoute.
"""
import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DISCORD_TOKEN", "test-local")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-local")

from loeil import config, vocal  # noqa: E402

TEXTE = ("Je suis L'Œil. Je vois tout, j'entends tout. "
         "Ce soir, chacun connaît sa mission. Personne ne recule.")


async def main() -> None:
    config.ELEVENLABS_API_KEY = getpass.getpass("Clé API ElevenLabs (rien ne s'affiche, c'est normal) : ").strip()
    config.ELEVENLABS_VOICE_ID = input("Voice ID : ").strip()
    sortie = Path(__file__).resolve().parent / "voix_test_elevenlabs.mp3"
    try:
        await vocal.synthetiser_elevenlabs(TEXTE, str(sortie))
    except Exception as exc:
        print(f"\nÉCHEC : {exc}")
        print("401 = clé invalide · 404 = Voice ID introuvable · 402/429 = quota ou abonnement")
        return
    print(f"\nOK ! Voix enregistrée dans {sortie}")
    if sys.platform == "win32":
        os.startfile(sortie)  # ouvre le fichier pour l'écouter


if __name__ == "__main__":
    asyncio.run(main())
