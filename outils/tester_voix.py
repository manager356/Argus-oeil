"""Test de la voix ElevenLabs de L'Œil, en local, sans Discord ni Railway.

Lancement (depuis le dossier Argus-oeil) :
    .venv\\Scripts\\python outils\\tester_voix.py

La clé et le Voice ID sont lus dans le presse-papiers (copie-les, rien à coller) ; rien n'est enregistré.
Le résultat est écrit dans outils\\voix_test_elevenlabs.mp3, puis ouvert pour l'écoute.
"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DISCORD_TOKEN", "test-local")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-local")

from loeil import config, vocal  # noqa: E402

TEXTE = ("Je suis L'Œil. Je vois tout, j'entends tout. "
         "Ce soir, chacun connaît sa mission. Personne ne recule.")


def presse_papier() -> str:
    """Ce qui est copié (Ctrl+C) en ce moment, lu via PowerShell : pas besoin de coller dans le terminal."""
    resultat = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                              capture_output=True, text=True, encoding="utf-8")
    return resultat.stdout.strip()


async def main() -> None:
    input("1) Copie ta CLÉ API ElevenLabs (Ctrl+C), puis appuie sur Entrée ici… ")
    config.ELEVENLABS_API_KEY = presse_papier()
    print(f"   Clé lue : {config.ELEVENLABS_API_KEY[:4]}…{config.ELEVENLABS_API_KEY[-3:]} "
          f"({len(config.ELEVENLABS_API_KEY)} caractères)")
    input("2) Copie maintenant le VOICE ID (Ctrl+C), puis appuie sur Entrée ici… ")
    config.ELEVENLABS_VOICE_ID = presse_papier()
    print(f"   Voice ID lu : {config.ELEVENLABS_VOICE_ID}")
    if not config.ELEVENLABS_API_KEY or not config.ELEVENLABS_VOICE_ID:
        print("\nLe presse-papiers était vide. Recommence en copiant bien avant d'appuyer sur Entrée.")
        return
    if config.ELEVENLABS_API_KEY == config.ELEVENLABS_VOICE_ID:
        print("\nTu as copié deux fois la même chose : la clé et le Voice ID doivent être différents.")
        return
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
