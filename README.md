# L'Œil

Bot Discord en Python pour le serveur RP. Il a quatre fonctions :

1. **Apaisement des tensions HRP** : dans les salons listés dans `TENSION_CHANNEL_IDS`, quand un message chaud apparaît (insultes, menaces, majuscules), L'Œil attend 45 s que la conversation se pose, puis fait juger les 20 derniers messages par Claude :
   - niveau 0-1 : rien ;
   - niveau 2 : message d'apaisement dans le salon ;
   - niveau 3 : apaisement + alerte dans le salon staff (`TENSION_STAFF_CHANNEL_ID`).

   Au maximum un message d'apaisement toutes les 30 min par salon.
   **Sanctions** : un joueur qui manque vraiment de respect à quelqu'un reçoit un avertissement public ; s'il recommence dans les `AVERTISSEMENT_HEURES` (24 h), il est mute `MUTE_MINUTES` (30 min) et le staff est prévenu. Le staff (admin / modérer les membres / gérer le serveur) n'est jamais sanctionné. Permission requise : **Exclure temporairement des membres** (Modérer les membres), et le rôle de L'Œil doit être au-dessus des rôles des joueurs. Les mots déclencheurs sont dans `loeil/tension.py`.
2. **Sondage de présence** : tous les jours à `PRESENCE_HOUR` (heure de Paris, 16:00 par défaut), il poste dans `PRESENCE_CHANNEL_ID` un sondage avec les boutons ✅ Présent / ❌ Absent / ⏳ Peut-être, mis à jour en direct. `/sondage-presence` (admins) le poste immédiatement.

3. **Discussion** : L'Œil répond quand on le mentionne ou qu'on répond à son message, et aux questions générales posées dans les salons (une réponse spontanée max toutes les 2 min par salon). Il s'appuie sur les annonces, les bilans de réunion et le salon objectifs, et n'invente rien. Quand un joueur dit qu'il n'y a rien à faire, il l'interroge sur ce qu'il a fait puis lui propose des actions concrètes. Personnalité : mystérieuse, phrases courtes. Modèle : `CHAT_MODEL` (Haiku par défaut).

4. **Missions du soir** : à `MISSIONS_HOUR` (20:00), les chefs (`MISSIONS_CHEF_IDS`) reçoivent en MP la liste des présents avec un bouton **Attribuer les missions** (formulaire « Pseudo : mission »). Chaque joueur reçoit sa mission en MP avec les boutons ✅ Accomplie / ❌ Pas pu la faire. À `RELANCE_HOUR` (23:00), ceux qui n'ont pas validé leur mission reçoivent un rappel en MP. À `RAPPORT_HOUR` (00:00), rapport dans le salon staff et en MP aux chefs. Commandes : `/missions` (liste maintenant), `/mission` (une mission à un joueur), `/rapport-missions`.

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
| `ANNONCES_CHANNEL_ID` | — | Salon des annonces que L'Œil lit pour répondre |
| `BILANS_CHANNEL_ID` | — | Salon des bilans de réunion (10 derniers lus) |
| `OBJECTIFS_CHANNEL_ID` | — | Salon des objectifs (défaut : celui du serveur) |
| `CHAT_MODEL` | — | `claude-haiku-4-5` par défaut |
| `CHAT_ENABLED` | — | `0` pour couper la discussion |
| `MISSIONS_CHEF_IDS` | — | ID Discord des chefs qui distribuent les missions (virgules) |
| `MISSIONS_HOUR` | — | Envoi de la liste des présents, `20:00` par défaut |
| `RELANCE_HOUR` | — | Rappel aux joueurs qui n'ont pas validé, `23:00` par défaut |
| `RAPPORT_HOUR` | — | Rapport des missions, `00:00` par défaut |
| `LEAD_IDS` | — | ID des leads (virgules) : réponse toujours garantie, jamais sanctionnés (les chefs des missions en font partie) |
| `SANCTIONS_ENABLED` | — | `0` pour couper avertissements et mutes |
| `MUTE_MINUTES` | — | Durée du mute, `30` par défaut |
| `AVERTISSEMENT_HEURES` | — | Durée de validité d'un avertissement, `24` par défaut |

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

Quand un mot déclencheur apparaît dans un salon surveillé, les 20 derniers messages de ce salon (pseudos + texte) sont envoyés à l'API Claude (Anthropic) pour être analysés. Pour répondre à une question, les 10 derniers messages du salon et les annonces sont envoyés à Claude.
