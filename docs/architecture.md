# Architecture d'Orchestra

## Processus
| Processus | Lancé par | Rôle |
|---|---|---|
| `python -m orchestra serve` | `start.ps1` | API FastAPI + WebSocket, Scribe (surveillance du coffre), planificateur, Gateway, runtime |
| `platform/notifier/notifier.py` | `start.ps1` | Notifications Windows à partir du flux d'alertes |
| `docker run orchestra-runtime …` | le runtime, à la demande | Exécution isolée du code d'un agent ou d'un skill (jetable) |
| Ollama | `start.ps1` (s'il n'écoute pas déjà) | Modèles locaux |

## Paquet `platform/orchestra`
| Module | Responsabilité |
|---|---|
| `platform.py` | Assemble tous les services (un objet `Platform` partagé par l'API et les tests) ; tâches de fond |
| `config.py` | Schéma de `config.yaml` (pydantic) ; refuse toute écoute non locale ; lecture de `.env` |
| `db.py` | SQLite WAL + FTS5 : agents, versions, messages, demandes, skills (+ versions, usages), tâches, budget, alertes, apprentissages, index des logs et du coffre |
| `permissions.py` | **Seul point d'autorisation** : matrice §5, communication §7, périmètre du coffre, portées de skills, outils de la fiche ; refus journalisés + alertes |
| `audit.py` | Journal `logs/AAAA-MM-JJ.jsonl` en ajout seul, chaîné par SHA-256, vérificateur d'intégrité |
| `redact.py` | Masquage des secrets et données personnelles ; recherche de secrets |
| `agents.py` | Création, modification versionnée, restauration, cycle de vie, promotion / rétrogradation |
| `messaging.py` | Messages, relais, demandes formelles, effets des décisions, escalade, anti-boucle, copies Obsidian |
| `budget.py` | Contrôle avant dépense, enveloppes, alertes 80 % / 100 %, synthèses |
| `gateway/` | LLM Gateway « compatible OpenAI » + chaîne de repli + coûts ; `demo/echo` hors ligne |
| `runtime/` | Prompt système (règles communes + fiche + skills + apprentissages), boucle d'outils JSON, bac à sable Docker / repli |
| `emergency.py` | Arrêt d'urgence persistant, reprise, test périodique |
| `scribe/` | Rendu des fiches, synchronisation coffre → base (watchdog), Git, recherche FTS5, journal lisible, décisions |
| `skills.py` | Cycle de vie des skills (auto-test, Vérificateur, portées, usage, versions, fusion, retrait) |
| `improvement.py` | Apprentissages, journal de bord, retour arrière automatique, promotion / échecs répétés, rapports quotidiens et hebdomadaires |
| `api/` | Routes REST, authentification par jeton, WebSocket, service du tableau de bord |
| `vault.py` | Arborescence du coffre, modèles de notes, dépôt Git du coffre (commits capturés, `git fast-import`) |

## Déroulé d'une tâche
1. `POST /api/agents/{id}/tasks` → `permissions: task.assign` → ligne `tasks` + log `assignation`.
2. Le runtime relit la **fiche courante** (version enregistrée sur la tâche), cherche les skills pertinents et les
   apprentissages, récupère les messages non lus (encadrés comme données), construit le prompt système.
3. Boucle : `gateway.chat` (contrôle d'urgence + budget **avant** l'appel, repli si quota) → réponse JSON →
   chaque outil est autorisé par la fiche (`tool.use`) puis exécuté par le service concerné, qui applique ses
   propres règles (messagerie, coffre, skills, bac à sable) → sorties d'outils renvoyées comme données (injections signalées).
4. Fin : résultat, coûts, note d'apprentissage, journal de bord ; événements temps réel pour la carte.
5. Validation (Propriétaire / hiérarchie) → statistiques de skills, retour arrière éventuel, promotion, échecs répétés.

## Données
- **Base** `data/orchestra.db` : état courant + index de recherche.
- **Journal** `logs/*.jsonl` : source de vérité infalsifiable (la base n'en est qu'un index).
- **Coffre** `Cerveau/` : représentation lisible et éditable par l'humain, versionnée par son propre dépôt Git.

## Temps réel
`EventBus` → WebSocket `/ws` : `agent_created`, `agent_updated`, `agent_activity`, `agent_level_changed`,
`message`, `request`, `task`, `skill`, `budget`, `alert`, `emergency`, `log`. Le tableau de bord recharge la vue
d'ensemble à chaque événement et anime les particules ; le notifier transforme les `alert` en notifications.

## Tâches de fond
| Période | Tâche |
|---|---|
| 1 min | Escalade des demandes en retard |
| 5 min | Commit Git global du coffre |
| 10 min | Rapports quotidien / hebdomadaire s'ils sont dus |
| 1 h | Vérification d'intégrité des logs ; test hebdomadaire de l'arrêt d'urgence s'il est dû |
