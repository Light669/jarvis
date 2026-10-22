# Activer les comptes et la sauvegarde en ligne

Sans configuration, Créapilot fonctionne en **mode démo** : les données restent dans le navigateur.
Avec Supabase, chaque client se connecte par e-mail (lien magique, sans mot de passe) et ses données sont sauvegardées en ligne.

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

## 4. Autoriser cette adresse dans Supabase

1. **Authentication** → **URL Configuration**.
2. **Site URL** : l’adresse de l’étape 3.
3. **Redirect URLs** : ajoute la même adresse.

## 5. Brancher l’application

1. **Project Settings** → **API** (ou **Data API**).
2. Copie :
   - **Project URL** (du type `https://abcd1234.supabase.co`)
   - la clé **anon public**
3. Dans `index.html`, remplis la ligne :
   ```js
   const CLOUD = { url: '', anonKey: '' };
   ```
   Tu peux aussi m’envoyer ces deux valeurs et je fais la modification.

La clé **anon public** peut être partagée : elle est faite pour être dans le navigateur, et les règles de la table empêchent chaque utilisateur de voir les données des autres.

> ⚠️ Ne partage jamais la clé **service_role** : elle donne un accès total à la base.

## Bon à savoir

- **E-mails de connexion** : Supabase envoie gratuitement quelques e-mails par heure seulement. C’est suffisant pour les premiers clients. Au-delà, branche un service d’envoi d’e-mails (par exemple Resend ou Brevo) dans **Authentication** → **Emails** → **SMTP Settings**.
- **Plusieurs appareils** : si le même compte modifie les données sur deux appareils en même temps, c’est la dernière modification enregistrée qui est gardée.
- **Une personne par compte** : pour l’instant, chaque compte a son propre espace. Le partage d’un espace entre plusieurs membres d’une équipe viendra plus tard.
