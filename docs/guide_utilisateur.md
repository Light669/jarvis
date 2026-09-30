# Guide du Propriétaire

## 1. Installer et lancer
1. Clonez le dépôt dans `C:\Orchestra`, ouvrez PowerShell dans ce dossier.
2. `.\detect.ps1` affiche votre machine et ce qui manque. `-Install` installe via winget (avec confirmation),
   `-Apply` règle le modèle local et le nombre d'agents simultanés dans `config.yaml`.
   Si PowerShell refuse les scripts : `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
3. Démarrez **Docker Desktop** (isolation des agents) et téléchargez le modèle conseillé : `ollama pull qwen2.5:7b`.
4. `.\start.ps1` : crée l'environnement Python, le jeton, le coffre, construit le tableau de bord et l'image
   d'exécution, lance l'API et le notifier, puis ouvre `http://127.0.0.1:8765` déjà connecté.
5. `.\stop.ps1` arrête tout (y compris les conteneurs d'agents en cours).

Le jeton est dans `.env` (`ORCHESTRA_TOKEN`). Le tableau de bord n'est accessible que depuis votre PC.

## 2. Ouvrir le second cerveau
Dans Obsidian : *Ouvrir un dossier comme coffre* → `C:\Orchestra\Cerveau`. Aucun plugin n'est obligatoire
(Dataview facultatif). La vue **Graphe** montre l'organisation réelle (fiches, messages, demandes, skills).

## 3. Créer un agent
- **Depuis la carte** : *Nouvel agent* → nom, niveau, supérieur (filtré selon le niveau), modèle, rôle,
  contexte, instructions, objectif, KPI, outils, coût maximum par jour, skills, interdits.
- **Depuis Obsidian** : copiez `Modeles_de_notes/agent.md` dans `Agents/<Niveau>/<nom>.md`, remplissez le
  frontmatter en laissant `id` vide, enregistrez. L'agent apparaît sur la carte ; son identifiant est écrit dans la note.

Règle de structure : un Responsable dépend du Chef, un Salarié d'un Responsable, un Apprenti d'un Salarié (son référent).

## 4. Modifier un agent
Cliquez sur l'agent → onglet **Fiche** → modifiez → *Enregistrer* (raison facultative). Chaque enregistrement
crée une version, un commit Git et une ligne de journal ; la nouvelle version est utilisée **dès la tâche suivante**.
*Restaurer* ramène une version précédente. Vous pouvez aussi modifier la note dans Obsidian : votre version gagne
toujours, l'ancienne reste dans Git.

Actions : Activer, Mettre en pause, Reprendre, Promouvoir, Rétrograder (indiquer le nouveau supérieur),
**Archiver** (licenciement : raison obligatoire ; rien n'est jamais supprimé, la fiche part dans `Archives/`).

## 5. Lire la carte
| Visuel | Signification |
|---|---|
| Contour qui pulse (indigo) | l'agent travaille |
| Grisé | inactif |
| Orange | en attente d'une réponse ou d'une validation |
| Rouge (qui tremble) | erreur, ou action refusée |
| Contour bleu | en pause |
| Bordure pointillée | brouillon |
| Particules sur les liens | message (indigo), demande (ambre), refus (rouge), acceptation (vert) |
| Lien pointillé entre deux agents | pairs qui ont échangé directement cette semaine |

*Réduire les animations* (en bas à gauche) coupe toutes les animations.

## 6. Confier et valider le travail
Onglet **Fiche** → *Confier une tâche*. Onglet **Activité** → résultat, puis *Valider* ou *Échec* (avec le point
d'échec). Ces validations alimentent la promotion (20 tâches à ≥ 85 %), la détection d'échecs répétés et le
**retour arrière automatique** : si une modification de fiche ou de skill fait chuter la réussite de plus de
15 points sur les 5 tâches suivantes, la version précédente est restaurée et une décision est consignée.

## 7. Demandes
Page **Demandes** : vous pouvez accepter ou refuser n'importe quelle demande. Une demande sans réponse depuis
24 h (réglable) monte d'un niveau, jusqu'à vous. Les demandes « plateforme » (modifier le code, les règles,
`config.yaml`) ne peuvent être validées **que par vous** — l'acceptation consigne une décision, l'application reste manuelle.

## 8. Budget
Page **Budget** : dépensé / plafond, seuil d'alerte (80 %), dépenses par jour, par agent, par modèle, et saisie
des dépenses et revenus (suivi micro-entreprise). À 100 %, toute dépense payante est bloquée ; les modèles locaux
et gratuits restent utilisables. Les enveloppes d'équipe se règlent sur la fiche du Responsable, le coût maximum
par jour sur chaque fiche.

## 9. Logs et alertes
Page **Logs** : recherche plein texte, filtres, export CSV, **Vérifier l'intégrité** (toute ligne modifiée,
supprimée ou tronquée est détectée). En ligne de commande : `python -m orchestra verify-logs`.
Les alertes (erreur grave, budget 80 %, demande en retard, action interdite, intégrité des logs, boucle de
messages, retour arrière…) s'affichent en notification Windows et sur la page **Alertes**. Canal e-mail : section
`alerts.email` de `config.yaml` (désactivé par défaut, mot de passe dans `.env`).

## 10. Arrêt d'urgence
Bouton rouge en haut de chaque page → confirmation → tous les agents sont gelés, les conteneurs tués, les appels
de modèles et accès externes coupés (en moins de 5 s). L'état survit à un redémarrage. Seul le Propriétaire
peut *Reprendre*. Le mécanisme est testé automatiquement chaque semaine (`POST /api/emergency/self-test` pour le
tester à la demande).

## 11. Modèles
Chaque fiche indique son modèle `fournisseur/modèle` (ex. `ollama/qwen2.5:7b`, `groq/llama-3.1-8b-instant`).
En cas de quota ou d'indisponibilité, le Gateway passe au suivant de `llm.fallback_chain`. Ajoutez vos clés
gratuites dans `.env`. `demo/echo` est un modèle hors ligne de démonstration.

## 12. Sauvegarde
Copiez `data/`, `logs/` et `Cerveau/` (avec son dossier `.git`). Le dépôt de la plateforme ne contient aucune donnée.
