---
type: accueil
---
# Orchestra — Second cerveau

Bienvenue dans le coffre central de la plateforme **Orchestra**. Tout ce que font les agents est ici, en Markdown, lié par des `[[wikilinks]]`.

| Dossier | Contenu |
|---|---|
| `Agents/<Niveau>/` | Une fiche par agent (Chef, Responsables, Salaries, Apprentis) |
| `Messages/<agent>/inbox` et `sent` | Copie de chaque message |
| `Demandes/` | Demandes formelles et leur statut |
| `Skills/{globaux,equipes,agents}/` | Compétences versionnées |
| `Apprentissages/` | Retours d'expérience après chaque tâche |
| `Decisions/` | Décisions du Chef d'Orchestre et leurs raisons |
| `Rapports/` | Rapports quotidiens et hebdomadaires |
| `Logs/AAAA-MM-JJ.md` | Journal lisible du jour (le journal infalsifiable est dans `logs/` à la racine) |
| `Budget/` | Dépenses, revenus, suivi micro-entreprise |
| `Modeles_de_notes/` | Modèles (agent, skill, demande, rapport) |
| `Archives/` | Agents licenciés, skills obsolètes (jamais supprimés) |

## Créer un agent depuis Obsidian
1. Copier `Modeles_de_notes/agent.md` dans `Agents/<Niveau>/<nom>.md`.
2. Remplir le frontmatter (laisser `id` vide : la plateforme l'attribue).
3. Enregistrer : le Scribe crée l'agent, qui apparaît sur la carte.

> Toute modification est versionnée (Git) et journalisée. En cas de conflit, la version du Propriétaire gagne.
