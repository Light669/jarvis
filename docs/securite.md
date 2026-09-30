# Revue de sécurité

| # | Exigence (§13) | Mise en œuvre | Preuve (tests) |
|---|---|---|---|
| 1 | Isolation | Code d'agent et de skill exécuté dans un conteneur jetable : `--network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --user 1000:1000 --cpus --memory --pids-limit`, délai maximal, **un seul volume** (`data/sandbox/<id>` → `/work`, supprimé après exécution). Aucun accès aux fichiers du Propriétaire. Sans Docker : sous-processus `python -I`, environnement vidé, délai — signalé `isolation=degradee` + alerte. | `test_docker_sandbox_isolation`, `test_sandbox_flags`, `test_subprocess_fallback` |
| 2 | Moindre privilège | Outils = outils de base du niveau + outils de la fiche ; chaque appel passe `tool.use`. Seuls le Chef et le Propriétaire modifient outils, budgets, niveaux. Un skill n'accorde jamais de droit. | `test_tools_from_fiche`, `test_tool_refused_when_not_in_fiche`, `test_skill_never_grants_rights_nor_contains_secrets` |
| 3 | Secrets | Uniquement dans `.env` (ignoré par Git). Masqués dans les logs (motifs + valeurs réelles de `.env`), messages, fiches, notes, skills (un skill contenant un secret est refusé). `scan-secrets` pour la recherche automatique. Journal d'accès d'uvicorn désactivé (le jeton du WebSocket passe dans l'URL). | `test_secrets_never_in_logs`, `test_12_no_secret_in_logs_or_vault`, `test_security_headers_and_token_not_logged` |
| 4 | Contenu externe = donnée | Sorties d'outils, messages reçus et skills injectés sont encadrés `<donnees …>` avec rappel ; motifs d'injection détectés → log `injection_signalee` + alerte. Un message ne peut jamais élever les droits (droits calculés par le code). | `test_injection_in_tool_output_is_flagged`, `test_unread_messages_are_given_as_data_and_injection_flagged`, `test_message_never_elevates_rights` |
| 5 | Accès local + jeton | Écoute `127.0.0.1` imposée par la config ; refus des clients non locaux ; `TrustedHostMiddleware` (anti *DNS rebinding*) ; aucun CORS ; jeton de 256 bits comparé à temps constant ; jeton transmis au navigateur par fragment d'URL, gardé en `sessionStorage` ; en-têtes `X-Frame-Options: DENY`, `nosniff`, `no-referrer`. | `test_config_refuses_network_exposure`, `test_api_requires_token`, `test_dns_rebinding_blocked`, `test_no_cors_for_foreign_origins` |
| 6 | Règles communes injectées | `runtime/prompts.py:COMMON_RULES` en tête de chaque prompt système (fraude, spam, RGPD, actions externes, budget, secrets, plateforme). | `test_task_uses_latest_instructions` |
| 7 | Arrêt d'urgence | Drapeau persistant, gel des tâches entre chaque étape et pendant l'appel au modèle (abandon < 0,1 s), conteneurs tués, Gateway et outils externes coupés ; reprise Propriétaire seul ; auto-test hebdomadaire. | `test_emergency_stop_under_5s`, `test_emergency_kills_containers`, `test_10_…` |
| 8 | Alertes | Erreur grave, budget 80 %/100 %, demande escaladée, action interdite, intégrité des logs (vérifiée toutes les heures), boucle de messages, injection, retour arrière, isolation dégradée → base + journal + WebSocket → notification Windows ; e-mail optionnel. | `test_notifier_shows_toasts_for_alerts`, `test_email_channel_optional`, `test_alert_on_log_integrity_check` |

## Garde-fous structurels
- **Permissions dans le code** : `permissions.py` est le seul point d'autorisation ; aucun prompt ne peut le contourner.
- **Journal infalsifiable** : ajout seul, chaîne SHA-256 + numéro de séquence + tête mémorisée en base → altération,
  suppression, réordonnancement et troncature détectés. Aucune route ne permet de modifier un log.
- **Plateforme non modifiable par les agents** : ni code, ni `config.yaml`, ni logs (hors coffre et hors périmètre) ;
  une demande `plateforme` ne peut être acceptée que par le Propriétaire.
- **Amélioration sans affaiblissement** : les agents ne modifient que les champs sûrs de leur fiche et leurs propres skills.

## Failles trouvées pendant la revue et corrigées
1. **Élévation de privilèges via le coffre** (grave) : une note écrite par un agent dans son dossier
   `Agents/<Niveau>/<nom>/…` aurait pu être importée par le Scribe comme une fiche créée par le Propriétaire.
   Correctif : seules les fiches `Agents/<Niveau>/<fichier>.md` sont importées ; les agents ne peuvent pas écrire
   de fiche. Test : `test_agent_note_in_workspace_cannot_create_or_modify_agents`.
2. **Jeton dans le journal d'accès HTTP** : le jeton du WebSocket (dans l'URL) aurait été écrit par uvicorn dans
   `logs/api.out.txt`. Correctif : `access_log=False` (toutes les actions restent dans le journal chaîné).
3. **Dépassement théorique du plafond** : l'estimation du coût avant appel est désormais prudente (≈ 2,5 caractères
   par token + `max_tokens` complet) pour que le coût réel ne dépasse jamais l'estimation contrôlée.
4. **Route masquée** (trouvée par la recette navigateur) : `/api/agents/{id}/{action}` interceptait `/tasks`.

## Limites connues
- En mode dégradé (sans Docker), le code d'un agent n'est pas isolé du réseau ni du système de fichiers : démarrez Docker Desktop.
- La détection d'injection repose sur des motifs : elle signale, mais la protection réelle reste l'application des droits par le code.
- `recherche_web` est volontairement non branchée : toute action externe doit être ajoutée par le Propriétaire.
