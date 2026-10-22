# Comment créer ton projet Claude « Créapilot »

Ce dossier contient tout ce qu’il faut pour retrouver le projet dans une nouvelle conversation Claude, sans rien réexpliquer.

## Ce qu’il y a dans le dossier

| Fichier | À quoi il sert |
|---|---|
| `01-INSTRUCTIONS-DU-PROJET.md` | Le texte à coller dans le champ **Instructions** du projet |
| `02-CONTEXTE-ET-ETAT.md` | Le projet en entier : l’idée, la cible, les prix, ce qui est fait, ce qui reste |
| `03-HISTORIQUE-DES-DECISIONS.md` | Comment on en est arrivé là, décision par décision |
| `04-VENTE-ET-PROSPECTION.md` | Le client idéal, la méthode de vente, les messages prêts à envoyer, les objections |
| `05-PRODUIT-ET-TECHNIQUE.md` | Les fonctions de l’appli, les comptes et services utilisés, comment modifier le site |
| `prospects.csv` | Les 27 marques et agences à contacter |
| `code/` | Le code du site, pour que Claude puisse le modifier |

## Étapes (5 minutes)

1. Va sur **claude.ai** et connecte-toi.
2. Dans le menu de gauche, clique sur **Projects** (Projets), puis sur **Create project** (Créer un projet).
3. Nom : `Créapilot`. Description : `CRM TikTok Shop pour les marques françaises`. Clique sur **Create project**.
4. À droite, dans **Instructions** (ou « Set project instructions ») :
   - ouvre `01-INSTRUCTIONS-DU-PROJET.md` avec le Bloc-notes ;
   - copie tout le texte qui se trouve sous la ligne `--- À COPIER ---` ;
   - colle-le, puis clique sur **Save**.
5. À droite, dans **Files** / **Project knowledge**, clique sur **+** puis **Upload from device**. Ajoute :
   - `02-CONTEXTE-ET-ETAT.md`
   - `03-HISTORIQUE-DES-DECISIONS.md`
   - `04-VENTE-ET-PROSPECTION.md`
   - `05-PRODUIT-ET-TECHNIQUE.md`
   - `prospects.csv`
   - tout le contenu du dossier `code/` (facultatif, mais utile si tu veux que Claude modifie l’appli)
6. Démarre une conversation dans le projet et écris par exemple :
   « Lis le contexte et dis-moi où on en est et quelle est la prochaine étape. »

## Tenir le projet à jour

Après une séance de travail importante, demande à Claude :
« Mets à jour le fichier 02-CONTEXTE-ET-ETAT.md avec ce qu’on vient de faire. »
Remplace ensuite l’ancien fichier par le nouveau dans le projet (supprime l’ancien, ajoute le nouveau).

## Les autres façons de ne rien perdre

- **Cette conversation reste dans Claude Code.** Tu la retrouves sur claude.ai/code, dans la liste des sessions. Elle ne disparaît pas quand tu fermes l’onglet.
- **Tout le travail est sauvegardé sur GitHub** :
  - le code source et ces fichiers : dépôt `light669/jarvis`, branche `claude/optimistic-goodall-1r2ew5` ;
  - le site en ligne : dépôt `Voxia-hub/CRM` (ton compte).
- **Pour modifier l’appli plus tard, le plus pratique est Claude Code** (claude.ai/code) relié à ton dépôt `Voxia-hub/CRM` : Claude modifie alors les fichiers et met le site à jour lui-même. Il faut connecter ton compte GitHub Voxia-hub à Claude (claude.ai → Paramètres → Connecteurs → GitHub).
- **Dans un projet Claude classique**, Claude ne peut pas modifier ton site directement. Il te donne les fichiers modifiés, et tu les envoies sur GitHub : dépôt `Voxia-hub/CRM` → **Add file** → **Upload files** → glisse le fichier → **Commit changes**. Un fichier qui porte le même nom remplace l’ancien.
