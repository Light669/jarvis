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
