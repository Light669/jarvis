# Décisions techniques

Chaque écart par rapport à l'architecture cible (§3 du cahier des charges) est justifié en 3 lignes.

## D1 — API, Scribe et Gateway sur l'hôte, Docker réservé à l'exécution isolée
- Sous Windows, les événements de fichiers d'un dossier monté dans Docker (bind-mount) ne remontent pas de façon fiable, or le coffre Obsidian vit sur l'hôte.
- L'API, le Scribe, le Gateway et le planificateur tournent donc dans un seul processus Python (venv) sur 127.0.0.1.
- Docker sert uniquement à ce qui doit être isolé : l'exécution des agents et des skills (`--network none`, lecture seule, non-root, limites CPU/RAM/PID).

## D2 — Ollama natif Windows
- Ollama natif utilise directement le GPU (CUDA/ROCm) sans configuration WSL/NVIDIA Container Toolkit.
- Il est plus simple à mettre à jour (`winget upgrade Ollama.Ollama`).
- Le Gateway l'appelle via son API compatible OpenAI (`http://127.0.0.1:11434/v1`).

## D3 — Repli d'isolation sans Docker
- Si Docker Desktop est arrêté ou absent, le code est exécuté en sous-processus confiné (dossier temporaire, délai maximal, variables d'environnement vidées).
- Chaque exécution est journalisée avec `isolation=degradee` et une alerte est levée une fois par session.
- Cela permet de démarrer et de tester sans Docker, sans jamais masquer la perte d'isolation.

## D4 — Un seul port, tableau de bord servi par l'API
- Le build Vite est servi par FastAPI sur `127.0.0.1:8765` : pas de CORS, un seul point d'entrée protégé par le jeton.
- Le jeton est transmis au navigateur par le fragment d'URL (`#token=…`, jamais envoyé au réseau ni journalisé), puis gardé en `sessionStorage`.
- Le développement du tableau de bord peut utiliser `npm run dev` (proxy Vite vers l'API).

## D5 — Paquet Python unique `orchestra`
- `platform/` contient un paquet `orchestra` avec les sous-paquets `api`, `runtime`, `gateway`, `scribe` (au lieu de dossiers indépendants) : un seul `pip install`, des imports simples, pas de collision avec le module standard `platform`.
- `platform/notifier/` et `platform/dashboard/` restent séparés (processus et langage différents).
- `platform/sandbox_image/` contient l'image Docker d'exécution.

## D6 — Coffre Obsidian hors du dépôt principal
- `Cerveau/` est généré au premier lancement à partir de `platform/orchestra/vault_template/` et possède son **propre** dépôt Git (commits automatiques du Scribe).
- Le dépôt de la plateforme l'ignore (`.gitignore`), ce qui évite de mélanger code et connaissance (et d'y pousser des données privées).
- Sauvegarde du coffre : copier `Cerveau/` (le dossier `.git` inclus) ou y ajouter un remote privé.

## D7 — Toutes les API LLM via le protocole « compatible OpenAI »
- Ollama, Groq, Gemini, OpenRouter et Mistral exposent tous `/chat/completions` compatible OpenAI.
- Un seul client HTTP (httpx) suffit ; changer de modèle = changer une chaîne `fournisseur/modèle` dans la fiche ou `config.yaml`.
- Les prix par million de tokens sont dans `config.yaml` pour le calcul des coûts.
