# Historique des décisions

Résumé de la conversation de départ avec Claude (22 octobre 2026), dans l’ordre.

## 1. Trouver l’idée

1. **Point de départ** : « créons quelque chose ensemble », avec l’objectif de gagner de l’argent.
2. **Choix du format** : un **micro-SaaS**, c’est-à-dire un logiciel en ligne vendu par abonnement mensuel. On réfléchit avant de coder, avec des questions posées une par une.
3. **Méthode retenue** : reprendre une idée qui marche déjà ailleurs, plutôt qu’inventer. Les clients existent déjà, donc c’est moins risqué.
4. **Envie de départ** : un CRM (logiciel de suivi de clients), à condition d’être sûr de pouvoir le vendre.
5. **Idée écartée** : un CRM pour restaurants avec une IA qui suit les tables. Le marché est difficile (beaucoup de concurrents, restaurateurs peu équipés, matériel nécessaire).
6. **15 idées rentables** étudiées, puis recherche de ce qui marche **aux États-Unis et en Chine mais pas encore en France**.
7. **Idées comparées** : CRM TikTok Shop, live shopping avec avatar IA, CRM WhatsApp pour commerces, logiciel pour toiletteurs, standard téléphonique IA.
8. **Décision : le CRM pour vendeurs TikTok Shop.**
   - C’est un CRM, ce qui correspondait à l’envie de départ.
   - Les clients sont faciles à trouver : ils sont sur TikTok.
   - Ils gagnent déjà de l’argent, donc ils peuvent payer.
   - Le marché français est tout neuf (depuis mars 2025), et il n’existe pas d’outil français.

## 2. Comprendre et valider

- Explication du principe du SaaS et du besoin réel, avec un diapo de 8 slides pour débutant.
- Je ne connais pas de vendeurs TikTok Shop, donc la prospection se fait à froid (LinkedIn, TikTok, Instagram).
- **Meilleur client** : une marque française de beauté, mode ou maison, avec 20 à 100 créateurs. Les agences viennent en deuxième.
- **Approche commerciale** : proposer un **test gratuit en échange d’un avis**, puis une prévente au tarif fondateur.

## 3. Construire

1. **MVP en 1 jour** : une appli qui fonctionne dans le navigateur.
2. **Branding** : nom provisoire « Créapilot », logo, couleurs, polices, puis nouvelle interface et tableau de bord.
3. **Améliorations**, acceptées une par une :
   - comptes et sauvegarde en ligne (Supabase) ;
   - rédaction des messages par IA sécurisée (Claude, avec la clé côté serveur) ;
   - page de vente avec formulaire fondateur ;
   - suivi des colis et du stock d’échantillons ;
   - démarrage guidé (« Bien démarrer ») ;
   - travail en équipe, choisi plutôt qu’une autre option ;
   - appli installable sur téléphone ;
   - import des ventes TikTok Shop ;
   - puis une pause et un récapitulatif.
4. **Diapo 15 slides** « Créapilot de A à Z » pour expliquer tout le projet.

## 4. Prospecter

- **Liste de 27 prospects** (`prospects.csv`) : marques (A), agences (B), à vérifier (C).
- **Recherches sur la liste A.** Claude ne peut pas ouvrir TikTok ni LinkedIn, donc la présence sur TikTok Shop reste à vérifier soi-même.
- **Ordre conseillé : For.Me, Blissim, Cut by Fred.** Ce sont des structures plus petites ou déjà actives avec des créateurs, qui décident vite.
- Messages personnalisés rédigés pour ces 3 marques.

## 5. Mettre en ligne

1. **Supabase** : projet `creapilot`, région Paris, créé et configuré par Claude. Les fonctions SQL avec suppression ont été collées à la main dans le SQL Editor.
2. **GitHub.** Le code source est sur le dépôt `light669/jarvis`, mais je suis connecté sur un autre compte GitHub, **Voxia-hub**. Décision : héberger le site sur **Voxia-hub/CRM** (public), avec les fichiers envoyés à la main depuis un zip.
3. **GitHub Pages** activé sur la branche `main` : https://voxia-hub.github.io/CRM/
4. **Supabase Authentication** : adresse du site renseignée pour la connexion par lien magique.
5. **Dossier de projet Claude** créé pour ne pas perdre la conversation (ce dossier).
