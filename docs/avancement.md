# Avancement de la construction

Environnement de construction : conteneur Linux (Python 3.11, Node 22, Docker 29, PowerShell 7.4 pour la vérification syntaxique des scripts `.ps1`).
Ce qui ne peut être prouvé que sur le PC Windows du Propriétaire est listé dans la section « À valider par le Propriétaire ».

## Phase 1 — Fondations ✅
**Livré**
- `detect.ps1` : OS, CPU, RAM, GPU/VRAM (`nvidia-smi` si présent), Git/Node/Python/Docker/Ollama/WSL2 ; recommandation du modèle local et du nombre d'agents simultanés ; rapport `docs/machine.md` ; `-Install` (winget, avec confirmation) ; `-Apply` (met à jour `config.yaml`).
- `config.yaml` validé par un schéma pydantic (`platform/orchestra/config.py`) ; refuse toute écoute hors 127.0.0.1.
- `start.ps1` / `stop.ps1` (+ `start.sh` / `stop.sh` pour Linux) : venv, dépendances, jeton local, coffre, build du tableau de bord, image runtime, Ollama, API, notifier, arrêt propre (y compris les conteneurs d'agents).
- `docker-compose.yml` + `platform/sandbox_image/Dockerfile` (image non-root `orchestra-runtime`).
- Coffre `Cerveau/` généré depuis `platform/orchestra/vault_template/` : arborescence §4, `00_Accueil.md`, modèles agent/skill/demande/rapport, `.obsidian/` minimal, dépôt Git dédié.

**Tests exécutés** : `pytest tests/test_phase1_foundations.py` → 9 réussis
- arborescence, `.env` ignoré, config valide et locale, refus de `0.0.0.0`, coffre complet + commit Git initial, idempotence (les modifications du Propriétaire ne sont pas écrasées), frontmatter du modèle d'agent, analyse syntaxique des 3 scripts PowerShell (pwsh 7.4).
- Image runtime construite (`docker compose --profile build-only build`) et exécutée avec `--network none --read-only --cap-drop ALL --user 1000:1000`.

## Phase 2 — Base, API, permissions, journal ✅
**Livré**
- `db.py` : SQLite WAL + FTS5 (agents, versions, messages, demandes, skills + versions + usages, tâches, budget, alertes, apprentissages, index des logs, index du coffre).
- `permissions.py` : **seul point d'autorisation** (`check` / `require`). Matrice §5 : création (Chef → responsables/salariés/apprentis ; Responsable → apprentis de son équipe), modification (champs sûrs sur sa propre fiche, champs d'équipe pour le Responsable, champs de structure/budget/outils réservés au Chef et au Propriétaire), cycle de vie, budget, décisions de demandes, périmètre du coffre, portées de skills, dépenses externes, outils de la fiche, arrêt d'urgence, communication §7. Tout refus → log `permission_refusee` + alerte. Personne ne peut modifier les logs ; la plateforme n'est modifiable que par le Propriétaire.
- `audit.py` : journal `logs/AAAA-MM-JJ.jsonl` en ajout seul, chaque ligne contient `prev_hash` + `hash` SHA-256 et un numéro de séquence ; `verify_chain` détecte altération, suppression, réordonnancement et (grâce à la tête mémorisée en base) troncature. CLI : `python -m orchestra verify-logs`.
- `redact.py` : masquage des secrets (clés Groq/OpenAI/Anthropic/Google/OpenRouter/GitHub, JWT, Bearer, clés privées, valeurs de `.env`) et des données personnelles (e-mail, téléphone, IBAN) dans les logs ; `scan-secrets` pour la recherche automatique.
- `agents.py` : création, modification versionnée (snapshot + log avant/après), restauration de version, cycle de vie `brouillon → actif ⇄ pause → archive` (jamais de suppression, raison d'archivage obligatoire), promotion / rétrogradation avec contrôle de structure.
- API FastAPI : jeton obligatoire (comparaison à temps constant), accès local uniquement, en-têtes de sécurité, journalisation de chaque action du tableau de bord ; routes agents, logs (recherche plein texte, filtres, export CSV, vérification d'intégrité), alertes, WebSocket `/ws` authentifié.

**Tests exécutés** : `pytest tests/` → 38 réussis (dont 29 pour la phase 2)
- matrice de permissions (création, modification, cycle de vie, dépenses, outils, coffre), refus journalisé + alerte ;
- versionnage et restauration, archivage sans suppression, promotion/rétrogradation ;
- chaîne de hash : altération, suppression de ligne, troncature, continuité après redémarrage ;
- masquage : aucun secret dans les logs ;
- API : 401 sans jeton, CRUD, pause, archivage sans raison refusé, recherche/filtre des logs, export CSV, WebSocket refusé sans jeton.

## Phase 3 — Runtime et LLM Gateway ✅
**Livré**
- `gateway/` : un seul client « compatible OpenAI » pour Ollama, Groq, Gemini, OpenRouter, Mistral (+ `MockProvider` hors ligne pour tests/démo). Chaîne de repli : modèle de la fiche → modèle par défaut → `fallback_chain`. Repli automatique sur quota (429), erreur serveur, fournisseur injoignable ou clé absente ; chaque repli est journalisé. Comptage tokens et euros (prix par million de tokens dans `config.yaml`). Appel abandonné en < 0,1 s si l'arrêt d'urgence est déclenché.
- `budget.py` : contrôle **avant** chaque dépense (plafond mensuel, budget du jour de l'agent, enveloppe mensuelle de l'équipe du Responsable) ; les modèles gratuits restent utilisables au-delà du plafond (dépense nulle) ; alerte `budget_80` et `budget_100` (une fois par mois) ; dépenses externes réservées aux Responsables/Chef/Propriétaire ; revenus (micro-entreprise) ; synthèse par agent, par modèle, par jour.
- `runtime/sandbox.py` : conteneur jetable `orchestra-runtime` (`--network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000 --cpus --memory --pids-limit`, un seul volume `/work`, délai maximal) ; repli en sous-processus signalé (`isolation=degradee` + alerte).
- `runtime/runner.py` : la fiche est relue **à chaque tâche** (contexte + instructions + règles communes §13 + skills pertinents + apprentissages récents) ; boucle d'outils JSON ; chaque outil contrôlé par la fiche (`tool.use`) ; sorties d'outils encadrées comme **données** ; détection de consignes suspectes (injection) → log + alerte ; nombre d'agents simultanés limité (`max_active_agents`) ; activité publiée pour la carte (travail / attente / erreur / gelé).
- `emergency.py` : gèle toutes les tâches, tue conteneurs et sous-processus, coupe les appels de modèles et les outils externes ; persiste après redémarrage ; reprise réservée au Propriétaire.
- API : tâches (assigner, suivre, valider), budget (synthèse, dépense, revenu), arrêt d'urgence / reprise.

**Tests exécutés** : `pytest tests/` → 52 réussis (dont 14 pour la phase 3)
- repli sur quota ; client HTTP (429 → repli, 503, clé absente) ; coûts ; alerte 80 % ; blocage à 100 % sans jamais dépasser le plafond ; budget journalier d'un agent ; dépense externe refusée à un salarié ;
- instructions modifiées prises en compte à la tâche suivante (version de fiche enregistrée sur la tâche) ;
- outil hors fiche refusé et journalisé ; injection signalée ;
- Docker réel : uid 1000, pas de réseau, système de fichiers en lecture seule, délai dépassé ; repli sous-processus ;
- **arrêt d'urgence : 2 tâches en cours gelées en < 5 s** (mesuré), conteneur Docker en cours tué en < 5 s, reprise refusée au Chef.
