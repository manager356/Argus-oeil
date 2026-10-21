"""Test de la voix ElevenLabs de L'Œil, en local, sans Discord ni Railway.

Lancement (depuis le dossier Argus-oeil) :
    .venv\\Scripts\\python outils\\tester_voix.py

La clé est collée dans le terminal (écran effacé ensuite) ; elle n'est enregistrée nulle part.
Le résultat est écrit dans outils\\voix_test_elevenlabs.mp3, puis ouvert pour l'écoute.
"""
import asyncio

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
    print("Colle avec Ctrl+V (ou clic droit), puis Entrée. Ne fais pas de capture d'écran de ta clé.\n")
    config.ELEVENLABS_API_KEY = (os.getenv("ELEVENLABS_API_KEY") or input("Clé API ElevenLabs : ")).strip()
    config.ELEVENLABS_VOICE_ID = (os.getenv("ELEVENLABS_VOICE_ID") or input("Voice ID : ")).strip()
    if not config.ELEVENLABS_API_KEY or not config.ELEVENLABS_VOICE_ID:
        print("\nLa clé ou le Voice ID est vide : rien n'a été collé. Recommence.")
        return
    if os.name == "nt":  # efface l'écran pour ne pas laisser la clé affichée
        os.system("cls")
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
