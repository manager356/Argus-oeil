import os
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        visible = sorted(
            k for k in os.environ.keys()
            if not k.startswith(("RAILWAY", "NIXPACKS", "_")) and k not in ("PATH", "HOME", "PWD", "HOSTNAME", "LANG", "TERM", "SHLVL", "OLDPWD")
        )
        raise RuntimeError(
            f"Variable d'environnement requise manquante : {name}. "
            f"Variables d'app visibles : {visible}"
        )
    return value


def _required_int(name: str) -> int:
    raw = _required(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} doit être un entier, reçu : {raw!r}") from exc


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} doit être un entier, reçu : {raw!r}") from exc


DISCORD_TOKEN: str = _required("DISCORD_TOKEN")
ANTHROPIC_API_KEY: str = _required("ANTHROPIC_API_KEY")
STAFF_CHANNEL_ID: int = _required_int("STAFF_CHANNEL_ID")
GUILD_ID: int | None = _optional_int("GUILD_ID")
