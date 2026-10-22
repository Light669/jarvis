# Produit et technique

## Les fonctions de l’application

- **Bien démarrer** : 5 étapes qui se cochent toutes seules (infos, créateurs, stock, premier message, première vente).
- **Tableau de bord** :
  - chiffres clés des 30 derniers jours, avec mini-graphiques ;
  - ventes par semaine, en graphique ou en tableau ;
  - « À faire aujourd’hui », avec les boutons Écrire / Fait ;
  - parcours des créateurs et classement des meilleurs.
- **Créateurs** :
  - colonnes Trouvés → Contactés → Échantillon envoyé → Vidéo postée → Génère des ventes ;
  - glisser-déposer ou bouton « Suivant » ;
  - filtres par catégorie, produit et « à relancer » ;
  - sur téléphone, des puces par étape.
- **Fiche créateur**, en 4 onglets :
  - Fiche : catégorie, abonnés, commission, produit, notes, historique ;
  - Colis ;
  - Ventes ;
  - Messages : modèles prêts à copier, « ✨ Rédiger avec l’IA » et « J’ai envoyé ce message ».
- **Relances automatiques** :
  - créateur trouvé depuis 5 jours ;
  - contacté depuis 3 jours sans suite ;
  - échantillon reçu depuis 7 jours sans vidéo.
- **Colis** : adresse, transporteur, numéro de suivi, dates d’envoi et de livraison, vue « À envoyer / En route / Livrés », stock d’échantillons par produit.
- **Import et export** :
  - créateurs depuis Excel ou Google Sheets (copier-coller ou fichier CSV) ;
  - export de la liste vers un tableur.
- **Import des ventes TikTok Shop** :
  - fichier CSV ou Excel, colonnes reconnues en français et en anglais ;
  - aucune commande comptée deux fois, commandes annulées ou remboursées ignorées.
- **Équipe** (version en ligne) : espace partagé par marque, invitations par e-mail, fusion automatique des modifications faites en même temps.
- **Inscrits** (administrateur seulement) : les marques inscrites depuis la page de vente.
- **Appli installable** sur téléphone et ordinateur.
- **Mode démo** : sans configuration, les données restent dans le navigateur, avec des créateurs d’exemple.

## Les fichiers du site (dossier `code/`)

| Fichier | Rôle |
|---|---|
| `index.html` | Page de vente : présentation, prix, FAQ, formulaire fondateur |
| `app.html` | L’application Créapilot complète (HTML, CSS et JavaScript dans un seul fichier) |
| `config.js` | Adresse du projet Supabase et clé « anon public » |
| `brand.html` | Guide de marque |
| `manifest.webmanifest`, `sw.js` | Installation sur téléphone |
| `assets/` | Logo, icônes, capture du tableau de bord |
| `supabase/schema.sql` | Structure de la base de données (tables, sécurité, fonctions) |
| `supabase/functions/generate-message/index.ts` | Fonction serveur qui fait rédiger les messages par Claude |
| `SUPABASE.md` | Guide pas à pas de la configuration Supabase |

C’est du HTML, du CSS et du JavaScript simples, sans outil de construction : un fichier modifié est en ligne dès qu’il est envoyé sur GitHub.

## Les comptes et services

| Service | Rôle | Détails |
|---|---|---|
| **GitHub, compte Voxia-hub** | Héberge le site en ligne | Dépôt public `Voxia-hub/CRM`, GitHub Pages sur la branche `main`, dossier racine |
| **GitHub, dépôt light669/jarvis** | Code source d’origine, créé avec Claude Code | Branche `claude/optimistic-goodall-1r2ew5` |
| **Supabase** | Comptes, base de données, fonction IA | Projet `creapilot`, région Paris, identifiant `xhgmwzomfjpgxcidfuww`, adresse https://xhgmwzomfjpgxcidfuww.supabase.co |
| **Anthropic** (facultatif) | IA qui rédige les messages | Clé à mettre dans Supabase → Edge Functions → Secrets → `ANTHROPIC_API_KEY`. Limite de 60 messages par compte et par jour |

Adresses en ligne :
- page de vente : https://voxia-hub.github.io/CRM/
- application : https://voxia-hub.github.io/CRM/app.html

Administrateur (onglet « Inscrits ») : sucrixcorp@gmail.com, dans la table `admins` de Supabase. Pour en ajouter un, va dans Supabase → SQL Editor et lance :
`insert into public.admins (email) values ('adresse@exemple.fr') on conflict do nothing;`

## Comment ça marche (version simple)

1. Le site (pages HTML) est hébergé gratuitement par GitHub Pages.
2. Quand quelqu’un se connecte, il reçoit un **lien magique** par e-mail (pas de mot de passe). C’est Supabase qui gère ça.
3. Chaque marque a un **espace** dans la base Supabase. Toutes ses données (créateurs, ventes, colis) y sont enregistrées, et partagées avec les membres de son équipe.
4. Les règles de sécurité de la base empêchent une marque de voir les données d’une autre.
5. Le formulaire de la page de vente enregistre les inscrits dans la table `leads`. Seuls les administrateurs peuvent les lire.
6. Pour l’IA, l’appli appelle la fonction serveur `generate-message`. La clé Anthropic reste cachée sur le serveur.

## Base de données (Supabase)

- **Tables** :
  - `workspaces`, `workspace_members`, `workspace_invites` : les espaces et les équipes ;
  - `leads` : les inscrits ;
  - `admins` : les administrateurs ;
  - `ai_usage` : le compteur d’utilisation de l’IA ;
  - `app_state` : l’ancien stockage, conservé pour la migration.
- **Fonctions** : `create_workspace`, `accept_invites`, `invite_member`, `cancel_invite`, `remove_member`, `save_workspace`, `is_member`, `is_owner`. Elles sont réservées aux utilisateurs connectés.

## Modifier le site

**Option 1 : Claude Code (le plus simple).** Ouvre claude.ai/code avec le dépôt `Voxia-hub/CRM` connecté. Claude modifie les fichiers et les met en ligne lui-même. Il faut d’abord connecter ton compte GitHub Voxia-hub à Claude.

**Option 2 : à la main.**
1. Demande à Claude le fichier modifié, en entier.
2. Va sur github.com/Voxia-hub/CRM → **Add file** → **Upload files**.
3. Glisse le fichier (même nom que l’ancien), puis clique sur **Commit changes**.
4. Attends 1 à 2 minutes, puis recharge le site avec **Ctrl + F5**.

⚠️ Pour un fichier qui va dans `assets/`, utilise cette adresse d’envoi : https://github.com/Voxia-hub/CRM/upload/main/assets

## Si la connexion par e-mail ne marche pas

1. Vérifie que tu ouvres bien https://voxia-hub.github.io/CRM/app.html, avec **CRM** en majuscules.
2. Vérifie dans Supabase → Authentication → URL Configuration :
   - Site URL : `https://voxia-hub.github.io/CRM/app.html`
   - Redirect URLs : `https://voxia-hub.github.io/**`
3. Regarde dans les spams. Le service d’e-mail gratuit de Supabase n’envoie que quelques e-mails par heure : attends un peu entre deux essais.
4. Ouvre le lien sur le même appareil et le même navigateur que ceux où tu l’as demandé.
5. Pour de vrais clients, configure plus tard un service d’envoi d’e-mails (Brevo ou Resend, par exemple) dans Supabase → Authentication → SMTP.
