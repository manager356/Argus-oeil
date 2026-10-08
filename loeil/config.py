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
GUILD_ID: int | None = _optional_int("GUILD_ID")


def _optional_int_list(name: str) -> list[int]:
    raw = os.getenv(name, "")
    try:
        return [int(x) for x in raw.replace(" ", "").split(",") if x]
    except ValueError as exc:
        raise RuntimeError(f"{name} doit être une liste d'ID séparés par des virgules, reçu : {raw!r}") from exc


# --- Apaisement des tensions HRP (désactivé si TENSION_CHANNEL_IDS est vide) ---
TENSION_CHANNEL_IDS: list[int] = _optional_int_list("TENSION_CHANNEL_IDS")
# Salon staff des alertes graves (STAFF_CHANNEL_ID accepté pour compatibilité)
TENSION_STAFF_CHANNEL_ID: int | None = _optional_int("TENSION_STAFF_CHANNEL_ID") or _optional_int("STAFF_CHANNEL_ID")
TENSION_STAFF_ROLE_ID: int | None = _optional_int("TENSION_STAFF_ROLE_ID")
TENSION_MODEL: str = os.getenv("TENSION_MODEL") or "claude-opus-5-5"

# --- Sondage de présence quotidien (désactivé si PRESENCE_CHANNEL_ID est vide) ---
PRESENCE_CHANNEL_ID: int | None = _optional_int("PRESENCE_CHANNEL_ID")
PRESENCE_ROLE_ID: int | None = _optional_int("PRESENCE_ROLE_ID")
PRESENCE_HOUR: str = os.getenv("PRESENCE_HOUR") or "16:00"

# --- Discussion : L'Œil répond aux questions à partir des annonces ---
ANNONCES_CHANNEL_ID: int | None = _optional_int("ANNONCES_CHANNEL_ID")
BILANS_CHANNEL_ID: int | None = _optional_int("BILANS_CHANNEL_ID")
# Salon des objectifs de l'orga (par défaut : celui du serveur RP)
OBJECTIFS_CHANNEL_ID: int | None = _optional_int("OBJECTIFS_CHANNEL_ID") or 1530622127596769371
# Salon privé où L'Œil note ce que le staff lui apprend (« @L'œil retiens : … »)
MEMOIRE_CHANNEL_ID: int | None = _optional_int("MEMOIRE_CHANNEL_ID") or 1556629021310058587
CHAT_MODEL: str = os.getenv("CHAT_MODEL") or "claude-opus-5-5"
# Mettre CHAT_ENABLED=0 pour couper la discussion
CHAT_ENABLED: bool = os.getenv("CHAT_ENABLED", "1") != "0"

# --- Sanctions : avertissement puis mute en cas de manque de respect ---
SANCTIONS_ENABLED: bool = os.getenv("SANCTIONS_ENABLED", "1") != "0"
MUTE_MINUTES: int = _optional_int("MUTE_MINUTES") or 30
# Durée pendant laquelle un avertissement compte (une récidive dans ce délai = mute)
AVERTISSEMENT_HEURES: int = _optional_int("AVERTISSEMENT_HEURES") or 24

# --- Missions du soir ---
# ID Discord des chefs qui reçoivent la liste des présents (séparés par des virgules). Vide = désactivé.
MISSIONS_CHEF_IDS: list[int] = _optional_int_list("MISSIONS_CHEF_IDS")
MISSIONS_HOUR: str = os.getenv("MISSIONS_HOUR") or "20:00"
RAPPORT_HOUR: str = os.getenv("RAPPORT_HOUR") or "00:00"
# Relance en MP de ceux qui n'ont pas validé leur mission (avant le rapport)
RELANCE_HOUR: str = os.getenv("RELANCE_HOUR") or "23:00"
# Analyse stratégique des points à suivre envoyée aux chefs avec la liste de 20h (0 = désactivée)
STRATEGIE_20H: bool = os.getenv("STRATEGIE_20H", "1") != "0"

# --- Leads : L'Œil leur répond toujours, avec déférence, et ne les sanctionne jamais ---
# (les chefs des missions en font automatiquement partie)
LEAD_IDS: set[int] = set(_optional_int_list("LEAD_IDS")) | set(MISSIONS_CHEF_IDS)

# --- Vocal : L'Œil parle en vocal sur ordre du staff / des leads ---
# Salon vocal par défaut (sinon il rejoint le vocal de la personne qui lui parle)
VOCAL_CHANNEL_ID: int | None = _optional_int("VOCAL_CHANNEL_ID")
VOIX_OEIL: str = os.getenv("VOIX_OEIL") or "fr-FR-HenriNeural"
VOIX_VITESSE: str = os.getenv("VOIX_VITESSE") or "-8%"
VOIX_HAUTEUR: str = os.getenv("VOIX_HAUTEUR") or "-6Hz"
