# Entretien Dynamique + Notation — Design

## Contexte

Le bot L'Œil conduit des entretiens de recrutement pour l'organisation Argus (serveur GTA FiveM RP).
Actuellement : 4 questions fixes en ordre strict, finalisation immédiate après Q4.

Objectif : transformer L'Œil en enquêteur actif qui creuse les réponses vagues,
forme son propre jugement, et remet un verdict structuré au staff.

---

## Comportement de L'Œil

- Les 4 questions de base sont toujours posées dans l'ordre, sans exception.
- Après chaque réponse, L'Œil juge si elle est suffisante.
  - Si vague, incohérente ou suspecte → relance ciblée, ton froid et incisif.
  - Aucune limite sur le nombre de relances — le candidat doit convaincre L'Œil.
- Une fois les 4 questions de base couvertes ET un jugement clair formé,
  L'Œil appelle `finalize_interview` à tout moment :
  - Immédiatement après Q4 si le jugement est limpide.
  - Après plusieurs relances si des doutes ont dû être levés.
  - Avant la fin des relances si le candidat est clairement inapte (après les 4 questions de base).
- Règle explicite dans le system prompt :
  *"Tu es le filtre d'Argus. Tu décides quand tu en sais assez. Ne finalise pas si tu as un doute non résolu."*

---

## Tool call `finalize_interview` — champs étendus

Champs existants (obligatoires, inchangés) :
- `answer_1` — réponse à Q1
- `answer_2` — réponse à Q2
- `answer_3` — réponse à Q3
- `answer_4` — réponse à Q4

Nouveaux champs (tous obligatoires) :
- `niveau` : `"PROFIL FORT"` | `"À SURVEILLER"` | `"REJETÉ"`
- `score` : entier 0–10
- `tags` : liste de strings (ex: `["loyal", "discret", "vague", "compétent"]`)
- `synthese` : jugement de L'Œil en 1 à 3 phrases, style froid et factuel

L'Œil ne peut pas appeler `finalize_interview` sans renseigner ces 4 champs.

---

## Embed staff enrichi

Couleur de l'embed selon le niveau :
- `PROFIL FORT` → vert (`0x22C55E`)
- `À SURVEILLER` → orange (`0xF59E0B`)
- `REJETÉ` → rouge (`0xEF4444`)

Structure de l'embed :
1. Titre : `Nouvelle candidature — [NIVEAU]`
2. Description : candidat + date + `Score : X/10` + tags entre crochets
3. Champ `Verdict de L'Œil` : contenu de `synthese`
4. Champs Q1–Q4 avec réponses (existant, inchangé)

---

## Fichiers modifiés

- `loeil/prompts.py` — system prompt étendu (comportement enquêteur + règle de finalisation)
- `loeil/llm_client.py` — `finalize_interview` tool étendu avec les 4 nouveaux champs
- `loeil/staff_channel.py` — `build_embed()` enrichi (couleur dynamique, score, tags, synthèse)

Aucun autre fichier touché. `interview.py`, `bot.py`, `config.py` — inchangés.

---

## Hors scope

- Persistance des notes (pas de base de données)
- Commande staff pour consulter les anciens entretiens
- Pondération personnalisable des tags
