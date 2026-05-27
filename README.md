# L'Œil — Bot de recrutement Argus

Bot Discord en Python pour les entretiens de recrutement de l'organisation Argus (roleplay GTA FiveM).

L'Œil est l'entité de surveillance d'Argus. Il ouvre un entretien en DM dès qu'un nouveau membre rejoint le serveur, ou quand quelqu'un tape `/postuler`. Il pose 4 questions, gérées par Gemini avec une personnalité froide et minimale. À la fin, il transmet le résumé au staff.

## Setup local

```powershell
# 1. Cloner le repo
git clone <url-repo> Argus-Loeil
cd Argus-Loeil

# 2. Créer un venv
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Mac/Linux

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer
copy .env.example .env
# Édite .env et remplis les valeurs

# 5. Lancer
python bot.py
```

## Variables d'environnement

| Variable | Obligatoire | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Token du bot Discord (Discord Developer Portal → Bot → Reset Token) |
| `GEMINI_API_KEY` | ✅ | Clé API Gemini (gratuite sur https://aistudio.google.com/apikey) |
| `STAFF_CHANNEL_ID` | ✅ | ID du channel où les candidatures sont postées (mode dev Discord → clic droit → Copier l'ID) |
| `GUILD_ID` | ⚠️ Recommandé | ID du serveur Argus (sync rapide des slash commands) |

## Tests

```powershell
pytest
```

## Déploiement Railway

1. Push le code sur GitHub
2. Sur https://railway.app : **New Project** → **Deploy from GitHub repo** → sélectionne `argus-loeil`
3. Onglet **Variables** : ajoute `DISCORD_TOKEN`, `GEMINI_API_KEY`, `STAFF_CHANNEL_ID`, `GUILD_ID`
4. Railway détecte `railway.toml` et lance `python bot.py` automatiquement

## Architecture

```
bot.py                   # Point d'entrée Discord, commande /postuler, on_member_join
loeil/
├── config.py            # Chargement des variables d'environnement
├── interview.py         # Orchestration des entretiens (état, flux, finalisation)
├── llm_client.py        # Wrapper Gemini + function calling
├── prompts.py           # System prompt de L'Œil + 4 questions + messages fixes
└── staff_channel.py     # Formatage et envoi du résumé staff
tests/                   # Tests unitaires (Gemini et Discord mockés)
```

## Comportement

- **Nouveau membre rejoint Argus** → L'Œil ouvre un DM et démarre l'entretien automatiquement (bots ignorés).
- **`/postuler` dans n'importe quel channel** → démarre un entretien en DM. Sert de backup si les DMs étaient fermés au moment du join.
- **DMs fermés** → L'Œil poste `@candidat Ouvre tes messages privés.` dans le channel système du serveur.
- **Entretien déjà en cours** → réponse "Un entretien est déjà en cours.", aucun nouvel entretien.
- **Hors-sujet** → géré par Gemini via son system prompt : "Ce n'est pas l'objet de cet entretien." puis répétition de la question en cours.
- **Fin d'entretien** → Gemini appelle le tool `finalize_interview(answer_1..answer_4)` → résumé posté dans le channel staff + message de clôture au candidat.

## Permissions Discord requises

Scopes OAuth2 : `bot`, `applications.commands`

Bot permissions : View Channels, Send Messages, Read Message History, Embed Links, Use Slash Commands

Intents (à activer dans Discord Developer Portal → Bot) :
- **Message Content Intent** (lecture des DMs)
- **Server Members Intent** (détection des nouveaux arrivants)
