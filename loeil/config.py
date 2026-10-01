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


def _optional_int_list(name: str) -> list[int]:
    raw = os.getenv(name, "")
    try:
        return [int(x) for x in raw.replace(" ", "").split(",") if x]
    except ValueError as exc:
        raise RuntimeError(f"{name} doit être une liste d'ID séparés par des virgules, reçu : {raw!r}") from exc


# --- Apaisement des tensions HRP (désactivé si TENSION_CHANNEL_IDS est vide) ---
TENSION_CHANNEL_IDS: list[int] = _optional_int_list("TENSION_CHANNEL_IDS")
# Salon des alertes niveau 3 (par défaut : le salon staff des candidatures)
TENSION_STAFF_CHANNEL_ID: int = _optional_int("TENSION_STAFF_CHANNEL_ID") or STAFF_CHANNEL_ID
TENSION_STAFF_ROLE_ID: int | None = _optional_int("TENSION_STAFF_ROLE_ID")
TENSION_MODEL: str = os.getenv("TENSION_MODEL") or "claude-opus-5-5"

# --- Sondage de présence quotidien (désactivé si PRESENCE_CHANNEL_ID est vide) ---
PRESENCE_CHANNEL_ID: int | None = _optional_int("PRESENCE_CHANNEL_ID")
PRESENCE_ROLE_ID: int | None = _optional_int("PRESENCE_ROLE_ID")
PRESENCE_HOUR: str = os.getenv("PRESENCE_HOUR") or "16:00"
