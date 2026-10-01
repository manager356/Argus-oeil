# L'Œil

Bot Discord en Python pour le serveur RP. Il a deux fonctions :

1. **Apaisement des tensions HRP** : dans les salons listés dans `TENSION_CHANNEL_IDS`, quand un message chaud apparaît (insultes, menaces, majuscules), L'Œil attend 45 s que la conversation se pose, puis fait juger les 20 derniers messages par Claude :
   - niveau 0-1 : rien ;
   - niveau 2 : message d'apaisement dans le salon ;
   - niveau 3 : apaisement + alerte dans le salon staff (`TENSION_STAFF_CHANNEL_ID`).

   Au maximum une intervention toutes les 30 min par salon, jamais de sanction automatique. Les mots déclencheurs sont dans `loeil/tension.py`.
2. **Sondage de présence** : tous les jours à `PRESENCE_HOUR` (heure de Paris, 16:00 par défaut), il poste dans `PRESENCE_CHANNEL_ID` un sondage avec les boutons ✅ Présent / ❌ Absent / ⏳ Peut-être, mis à jour en direct. `/sondage-presence` (admins) le poste immédiatement.

## Variables d'environnement

| Variable | Obligatoire | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Token du bot |
| `ANTHROPIC_API_KEY` | ✅ | Clé API Claude |
| `GUILD_ID` | Recommandé | ID du serveur (commandes slash disponibles tout de suite) |
| `TENSION_CHANNEL_IDS` | — | ID des salons HRP surveillés, séparés par des virgules |
| `TENSION_STAFF_CHANNEL_ID` | — | Salon des alertes graves |
| `TENSION_STAFF_ROLE_ID` | — | Rôle pingé lors d'une alerte grave |
| `TENSION_MODEL` | — | `claude-opus-5-5` par défaut ; `claude-haiku-4-5` est environ 4 fois moins cher |
| `PRESENCE_CHANNEL_ID` | — | Salon du sondage |
| `PRESENCE_ROLE_ID` | — | Rôle pingé par le sondage |
| `PRESENCE_HOUR` | — | Heure du sondage, `16:00` par défaut |

Intent requis (Developer Portal → Bot) : **Message Content Intent**.

## Lancer en local

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # puis remplir
.venv\Scripts\python bot.py
```

Tests : `.venv\Scripts\python -m pytest`

## Déploiement Railway

Railway lit `railway.toml` et le `Dockerfile`, puis lance `python bot.py`. Les variables se règlent dans l'onglet **Variables**.

## Vie privée

Quand un mot déclencheur apparaît dans un salon surveillé, les 20 derniers messages de ce salon (pseudos + texte) sont envoyés à l'API Claude (Anthropic) pour être analysés.
