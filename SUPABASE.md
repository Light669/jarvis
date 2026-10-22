# Activer les comptes et la sauvegarde en ligne

> **État du projet Supabase « creapilot » (créé le 22 octobre 2026, région Paris)**
>
> Déjà fait :
> - projet créé dans l’organisation gratuite ;
> - tables, règles de sécurité et fonctions `is_member` / `is_owner` installées ;
> - fonction d’IA `generate-message` déployée ;
> - ton adresse e-mail déclarée administrateur (onglet « Inscrits ») ;
> - `config.js` rempli avec l’adresse du projet et la clé « anon public ».
>
> Il reste à faire :
> 1. **SQL Editor** : coller tout `supabase/schema.sql`, puis **Run** (et confirmer si Supabase le demande). Cela installe les fonctions de l’équipe et de sauvegarde.
> 2. **GitHub Pages** : mettre le site en ligne (étape 3 ci-dessous).
> 3. **Authentication → URL Configuration** : renseigner l’adresse de l’application (étape 4).
> 4. Facultatif, pour l’IA : ajouter le secret `ANTHROPIC_API_KEY` (étape 6).

Sans configuration, Créapilot fonctionne en **mode démo** : les données restent dans le navigateur.
Avec Supabase, chaque client se connecte par e-mail (lien magique, sans mot de passe) et ses données sont sauvegardées en ligne. Le formulaire de la page de vente enregistre aussi les inscriptions.

Compte 15 minutes.

## 1. Créer le projet Supabase (gratuit)

1. Va sur [supabase.com](https://supabase.com) et crée un compte.
2. Clique sur **New project**.
   - Nom : `creapilot`
   - Région : **West EU (Paris)**, pour garder les données en Europe.
   - Choisis un mot de passe de base de données et garde-le de côté.
3. Attends 1 à 2 minutes que le projet soit prêt.

## 2. Créer la table

1. Menu de gauche : **SQL Editor** → **New query**.
2. Colle le contenu du fichier [`supabase/schema.sql`](supabase/schema.sql).
3. Clique sur **Run**. Le message « Success » doit s’afficher.

## 3. Mettre l’application en ligne

Le lien de connexion envoyé par e-mail doit ramener vers une vraie adresse web (il ne fonctionne pas depuis l’aperçu dans Claude).

1. Sur GitHub, dans ce dépôt : **Settings** → **Pages**.
2. Source : **Deploy from a branch**, branche `main` (ou la branche de travail), dossier `/ (root)`.
3. Note l’adresse obtenue, par exemple `https://light669.github.io/jarvis/`.
   - La page de vente est à cette adresse.
   - L’application est à la même adresse suivie de `app.html`, par exemple `https://light669.github.io/jarvis/app.html`.

## 4. Autoriser cette adresse dans Supabase

1. **Authentication** → **URL Configuration**.
2. **Site URL** : l’adresse de l’application (celle qui finit par `app.html`).
3. **Redirect URLs** : ajoute la même adresse.

## 5. Brancher l’application

1. **Project Settings** → **API** (ou **Data API**).
2. Copie :
   - **Project URL** (du type `https://abcd1234.supabase.co`)
   - la clé **anon public**
3. Dans le fichier `config.js`, remplis les deux valeurs :
   ```js
   window.CREAPILOT_CONFIG = {
     supabaseUrl: 'https://abcd1234.supabase.co',
     supabaseAnonKey: 'la-clé-anon-public',
   };
   ```
   Ce fichier sert à la fois à l’application et à la page de vente. Tu peux aussi m’envoyer ces deux valeurs et je fais la modification.
4. **Voir les inscrits de la page de vente** : connecte-toi une première fois à l’application avec ton adresse e-mail, puis dans **SQL Editor**, exécute (avec ton adresse) :
   ```sql
   insert into public.admins (email) values ('ton.adresse@exemple.fr') on conflict do nothing;
   ```
   Recharge l’application : un onglet **Inscrits** apparaît dans la barre latérale, avec la liste des marques qui ont rempli le formulaire.

La clé **anon public** peut être partagée : elle est faite pour être dans le navigateur, et les règles de la table empêchent chaque utilisateur de voir les données des autres.

> ⚠️ Ne partage jamais la clé **service_role** : elle donne un accès total à la base.

## 6. Activer la rédaction par IA (facultatif)

Le bouton « ✨ Rédiger avec l’IA » (onglet **Messages** de chaque créateur) écrit un message sur mesure avec Claude.
La clé de l’IA reste sur Supabase : elle n’est jamais envoyée au navigateur.

1. **Clé d’API Anthropic** : crée un compte sur [console.anthropic.com](https://console.anthropic.com), ajoute un moyen de paiement, puis **API Keys** → **Create Key**.
   Dans **Limits**, fixe une limite de dépense mensuelle (par exemple 20 €) pour ne jamais avoir de surprise.
2. **Créer la fonction** : dans Supabase, **Edge Functions** → **Deploy a new function** → **Via Editor**.
   - Nom : `generate-message` (exactement).
   - Colle le contenu de [`supabase/functions/generate-message/index.ts`](supabase/functions/generate-message/index.ts), puis **Deploy**.
3. **Ajouter la clé** : **Edge Functions** → **Secrets** → **Add new secret**.
   - Nom : `ANTHROPIC_API_KEY`
   - Valeur : la clé de l’étape 1.
   - Facultatif : `AI_DAILY_LIMIT` pour changer la limite de messages IA par compte et par jour (60 par défaut).
4. Vérifie que le script SQL de l’étape 2 a bien été relancé avec la table `ai_usage` (il peut être exécuté plusieurs fois sans risque).

Avec l’outil en ligne de commande Supabase, l’équivalent est :

```bash
supabase functions deploy generate-message
supabase secrets set ANTHROPIC_API_KEY=sk-ant-...
```

**Coût** : environ 1 centime par message rédigé. La limite quotidienne par compte et la limite de dépense Anthropic protègent contre les abus.

**Sécurité** : si une demande est bloquée par un filtre de sécurité de l’IA, la fonction réessaie automatiquement avec un autre modèle Claude ; si elle est encore refusée, l’utilisateur voit un message lui demandant de reformuler.

## 7. Travailler en équipe

Chaque compte a un **espace** : la première connexion le crée, et la personne qui le crée en est propriétaire.

1. Dans l’application, onglet **Équipe** : saisis l’adresse e-mail d’un collègue puis **Inviter**.
2. Envoie-lui le lien de l’application (bouton « Copier le lien de l’application »). Aucun e-mail d’invitation n’est envoyé automatiquement.
3. Ton collègue se connecte avec **cette adresse e-mail** : il rejoint ton espace automatiquement et voit les mêmes créateurs, colis et ventes.

Bon à savoir :
- Si deux personnes modifient en même temps, l’application **fusionne les changements créateur par créateur**. Si les deux modifient le même créateur, c’est la modification la plus récente qui est gardée.
- Les changements des collègues apparaissent automatiquement en moins de 30 secondes.
- Chacun signe ses messages avec son propre prénom, et l’historique de chaque créateur indique qui a fait quoi.
- Seul le propriétaire peut inviter ou retirer des membres.
- Une personne invitée dans plusieurs espaces (une agence, par exemple) choisit l’espace dans la barre latérale.
- Les comptes créés avant cette mise à jour retrouvent leurs données : elles sont reprises dans leur espace à la première connexion.

Le script `supabase/schema.sql` contient les tables de l’équipe : relance-le en entier dans **SQL Editor** après chaque mise à jour (il peut être exécuté plusieurs fois sans risque).

## Bon à savoir

- **E-mails de connexion** : Supabase envoie gratuitement quelques e-mails par heure seulement. C’est suffisant pour les premiers clients. Au-delà, branche un service d’envoi d’e-mails (par exemple Resend ou Brevo) dans **Authentication** → **Emails** → **SMTP Settings**.
- **Plusieurs appareils** : comme pour une équipe, les modifications faites en même temps sur deux appareils sont fusionnées créateur par créateur.
