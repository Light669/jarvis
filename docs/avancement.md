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

## Phase 4 — Messagerie et demandes ✅
**Livré** (`messaging.py`, `scribe/writer.py`)
- Règles §7 appliquées par `permissions.can_message` : ligne hiérarchique directe ; pairs du même niveau **et** de la même équipe (les Responsables entre eux) ; sinon refus avec consigne « passer par son supérieur » ; le Chef et le Propriétaire écrivent à tous ; seul le Chef écrit au Propriétaire. **Relais** par le supérieur (avec ses propres droits, trace `relaye_de`).
- Messages : `id, de, a, sujet, corps, thread_id, priorite, horodatage, statut (envoye/lu/traite)` ; secrets masqués ; événement temps réel (particules sur la carte).
- Demandes formelles (`acces_outil, budget, aide, validation, skill_equipe, promotion, plateforme`) avec justification, gain attendu, coût ; statut `en_attente / acceptee / refusee / escaladee` ; effets appliqués **avec les droits du décideur** — si le décideur n'en a pas le droit (ex. un Responsable ne peut pas accorder d'outil), la demande est escaladée avec son avis favorable ; les demandes « plateforme » vont directement au Propriétaire, seul habilité à les valider.
- Escalade automatique toutes les minutes : demande sans réponse depuis `escalation_hours` → niveau supérieur (jusqu'au Propriétaire) + alerte.
- Anti-boucle : quota de messages par agent et par heure, profondeur maximale d'un fil → blocage + log `boucle_bloquee` + alerte.
- Copie dans Obsidian : `Messages/<agent>/inbox|sent/`, `Demandes/`, avec frontmatter et `[[wikilinks]]` vers les fiches. Commit Git périodique (5 min).
- Outils d'agents `envoyer_message` et `faire_demande` branchés sur ces règles.
- API : messages (liste, fil, envoi, relais), demandes (en attente, décision, escalade immédiate).

**Tests exécutés** : `pytest tests/` → 78 réussis (dont 26 pour la phase 4)
- matrice de 12 cas de communication (dont apprenti → autre niveau / autre équipe **refusé et journalisé**) ; relais ; seul le Chef écrit au Propriétaire ;
- un message ne donne aucun droit ; secrets masqués dans la base et le coffre ;
- demande d'outil : responsable → escalade automatique → Chef → outil accordé ; refus ; escalade après délai (horloge simulée) jusqu'au Propriétaire avec alerte ; demande « plateforme » refusée au Chef ; promotion par demande ;
- boucle infinie ping-pong bloquée par le quota horaire ; limite de profondeur d'un fil ;
- outils `envoyer_message` depuis une tâche (autorisé + refusé) ; API.

## Phase 5 — Scribe ✅
**Livré** (`scribe/scribe.py`, `scribe/writer.py`, `vault.py`)
- **Base → coffre** : chaque création / modification / promotion / archivage réécrit la fiche `Agents/<Niveau>/<nom>.md` (frontmatter §6 + sections Rôle, Contexte, Instructions, Objectif et KPI, Interdits, Journal de bord) ; ligne de liens `[[supérieur]]`, `[[équipe]]`, `[[subordonnés]]` pour que le graphe Obsidian montre l'organisation ; la fiche du supérieur est mise à jour ; promotion = déplacement de la note ; archivage = déplacement dans `Archives/Agents/` (jamais supprimée).
- **Coffre → base** : surveillance `watchdog` (anti-rebond 0,5 s) ; une fiche modifiée à la main est validée puis appliquée **au nom du Propriétaire** (version +1, log avant/après) ; une nouvelle note dans `Agents/…` crée l'agent (identifiant réécrit dans la note) ; une note invalide est refusée avec alerte ; une fiche supprimée est restaurée (un agent n'est jamais supprimé) ; anti-écho par hash (le Scribe ignore ses propres écritures).
- **Conflits** : la version du Propriétaire gagne ; la version précédente reste dans l'historique Git.
- **Git** : un commit par changement de fiche, avec le contenu **capturé au moment du changement** (écrit en arrière-plan via `git fast-import`, donc sans ralentir les agents) ; commit global périodique pour le reste.
- **Périmètre** : `write_as` / `write_agent_note` n'autorisent un agent que dans son dossier `Agents/<Niveau>/<nom>/` ; lecture : son dossier, son équipe pour un Responsable, tout pour le Chef, zones partagées (Skills, Apprentissages, Modèles).
- **Mémoire consultable** : index FTS5 du coffre (`/api/search`, outil `chercher_memoire`), filtré par les droits de lecture de l'agent ; réindexation au démarrage.
- **Journal lisible du jour** `Logs/AAAA-MM-JJ.md` alimenté en direct par le journal infalsifiable.
- **Décisions** dans `Decisions/` (commit Git).

**Tests exécutés** : `pytest tests/` → 91 réussis (dont 13 pour la phase 5)
- fiche écrite à la création (frontmatter, sections, wikilinks, fiche du supérieur, commit) ; modification par formulaire → note + commit v2 ;
- **modification manuelle dans Obsidian** → base mise à jour au nom du Propriétaire, anti-écho, ancienne version récupérable dans Git ;
- **création d'un agent depuis une note** (modèle de note) ; note invalide refusée + alerte ; fiche supprimée restaurée ; promotion et archivage déplacent les notes ;
- apprenti : écriture dans son dossier OK, 4 tentatives hors périmètre **refusées et journalisées** ; lecture hors équipe refusée ;
- recherche plein texte filtrée par droits ; journal lisible du jour ; **surveillance en direct** (modification et création détectées en < 5 s) ; API recherche / historique / lecture de note.

## Phase 6 — Tableau de bord ✅
**Livré** (`platform/dashboard/`, React 18 + Vite + TypeScript + React Flow 12 + Framer Motion + Tailwind, thème sombre)
- **Carte animée** : Chef en haut, puis Responsables, Salariés, Apprentis (placement hiérarchique automatique) ; liens hiérarchiques + **liens entre pairs en pointillés** (pairs ayant échangé dans les 7 derniers jours) ; regroupement par équipe ; zoom, déplacement, mini-carte.
- **États** : pulsation quand l'agent travaille, grisé inactif, orange en attente, rouge en erreur (avec secousse), **contour bleu en pause**, bordure pointillée en brouillon, gelé pendant l'arrêt d'urgence. **Particules** animées le long des liens pour chaque message (indigo), demande (ambre), refus (rouge), acceptation (vert) ; nœud qui tremble lors d'un refus de permission. Animations de création (apparition), promotion (badge qui change) et archivage (fondu). Badge de niveau et **jauge de budget** journalier sur chaque nœud. Option **« Réduire les animations »** (respecte aussi la préférence système).
- **Panneau latéral** (clic sur un agent), 6 onglets : Fiche (tous les champs modifiables, raison, enregistrement versionné, **restaurer une version**, activer / pause / reprendre / promouvoir / rétrograder / archiver, confier une tâche) ; Activité en direct (état, tâches + validation réussite/échec, flux d'événements) ; Messages et demandes (fils, écrire en tant que Propriétaire) ; Skills ; Historique (commits Git de la fiche + journal) ; Coûts (jour, mois, tokens).
- **Nouvel agent** : formulaire complet (nom, niveau, supérieur filtré par niveau, modèle, rôle, contexte, instructions, objectif, KPI, outils, coût max/jour, enveloppe d'équipe, skills, interdits).
- **Pages** : Logs (recherche plein texte, filtres agent / niveau / type / gravité / dates, mise à jour en direct, export CSV, vérification d'intégrité), Budget (jauge avec seuil 80 %, dépensé / reste / revenus, dépenses par jour avec vue tableau, par agent, par modèle, saisie de dépense / revenu), Demandes (en attente avec accepter / refuser, historique, escalade manuelle), Skills, Alertes.
- **Arrêt d'urgence** visible sur **toutes les pages** (barre du haut, confirmation), bandeau rouge tant qu'il est actif, reprise par le Propriétaire.
- Sécurité : écran de connexion par jeton ; le jeton arrive par le fragment `#token=` (jamais envoyé au réseau), gardé en `sessionStorage` ; WebSocket authentifié avec reconnexion automatique.
- Ajouts backend : `/api/overview` (carte en un appel), fournisseur hors ligne `demo/echo`, commande `python -m orchestra demo` (organisation de démonstration).
- Correctif trouvé par la recette navigateur : la route générique `/api/agents/{id}/{action}` masquait `/tasks` → enregistrée en dernier (test de non-régression ajouté).

**Tests exécutés**
- `npm run build` (vérification TypeScript stricte + build Vite) : OK.
- `pytest tests/` → 93 réussis, dont **`tests/e2e/test_dashboard.py`** (Chromium réel + serveur uvicorn réel) : jeton invalide refusé ; carte affichée avec liens entre pairs ; clic sur un agent → modification des instructions → **v2 sur la carte, en base et dans la note Obsidian** ; parcours des 6 onglets ; **création via le formulaire → nœud sur la carte + fiche dans le coffre** ; tâche exécutée ; 5 pages ; **arrêt d'urgence depuis une page quelconque en < 5 s** puis reprise ; actions du tableau de bord journalisées ; aucune erreur JavaScript.
- Captures : `docs/captures/` (carte, panneau, logs, budget, arrêt d'urgence).
