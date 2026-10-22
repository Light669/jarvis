# Créapilot : contexte et état du projet

*Dernière mise à jour : 22 octobre 2026*

## En une phrase

**Créapilot** est un CRM en français, vendu par abonnement, pour les marques qui vendent sur **TikTok Shop**. Il les aide à gérer leurs **créateurs affiliés** : qui contacter, qui a reçu l’échantillon, qui a posté sa vidéo, qui relancer, qui génère des ventes et combien de commission lui verser.

Slogan : **« Pilote tes créateurs, pas ton tableur. »**

## Le problème qu’on résout

- TikTok Shop est arrivé en France en **mars 2025**. Les ventes passent surtout par des **créateurs affiliés** : ils reçoivent le produit gratuitement, font une vidéo, et touchent une commission sur chaque vente.
- Une marque travaille avec **30 à 50 créateurs**, parfois beaucoup plus. Elle les suit aujourd’hui dans Excel et dans des messages éparpillés.
- Résultat : des échantillons envoyés qui ne donnent jamais de vidéo, des relances oubliées, et aucune idée de qui rapporte vraiment.
- Aux États-Unis et en Chine, des outils existent (Euka, Reacher, FastMoss, Kalodata). **En France, on n’a trouvé aucun outil spécialisé** en français.

## Le marché (chiffres de blogs spécialisés, à confirmer)

- 16 000 à 35 000 boutiques TikTok Shop actives en France, selon les sources.
- 30 à 50 créateurs à gérer par marque, selon les guides vendeurs.
- Risques : dépendance à TikTok (API, règles, réglementation européenne).

## Le client idéal

1. **Cible n°1** : une marque française de beauté, soin, mode ou maison, qui vend déjà sur TikTok Shop et travaille avec 20 à 100 créateurs. Petite équipe de 1 à 15 personnes, avec une seule personne débordée qui gère les créateurs. On contacte le fondateur ou le responsable influence / TikTok Shop / affiliation.
2. **Cible n°2** (plus tard) : les agences TikTok Shop qui gèrent plusieurs marques.
3. **À éviter au début** : les petits vendeurs (moins de 10 créateurs), les créateurs eux-mêmes et les grandes marques.

Détails et messages : voir `04-VENTE-ET-PROSPECTION.md`.

## Les prix

| Formule | Prix | Contenu |
|---|---|---|
| Débutant | 49 €/mois | 1 boutique, jusqu’à 50 créateurs |
| **Pro** | 99 €/mois | 300 créateurs, IA, installation faite pour le client |
| Agence | 199 €/mois | Plusieurs boutiques, créateurs illimités |

**Offre fondateur** (5 places) : 14 jours gratuits, installation faite pour eux, puis **Pro à 49 €/mois à vie**, sans engagement.

Exemple : 50 clients × 99 € ≈ 4 950 € par mois. Coûts de départ très faibles : hébergement gratuit, IA ≈ 1 centime par message.

## La marque

- Couleurs : **Grenadine** #E8264F (couleur principale), **Aubergine** #22152F (fond foncé, texte), **Menthe** #1BAF7A (succès, ventes), **Lilas** #F6F4F9 (fond clair).
- Polices : **Bricolage Grotesque** pour les titres, **Figtree** pour le texte.
- Logo : un arc en forme de « C » avec un point.
- Ton : direct, chaleureux, concret, en tutoyant les utilisateurs.

## Ce qui est fait ✅

**Le produit**
- Application complète : tableau de bord, créateurs par étape, relances, colis et stock, messages prêts à copier, rédaction par IA, import de créateurs et des ventes TikTok Shop, équipe, appli installable sur téléphone, onglet « Inscrits ».
- Page de vente avec les prix, une FAQ et un formulaire « Réserver ma place fondateur ».
- Guide de marque.

**La mise en ligne**
- **Supabase** (base de données et connexion) : projet `creapilot`, région Paris. Tables, règles de sécurité, 8 fonctions et la fonction d’IA `generate-message` sont installées. L’adresse sucrixcorp@gmail.com est déclarée administrateur.
- **Site en ligne avec GitHub Pages**, sur le compte GitHub **Voxia-hub**, dépôt **CRM** :
  - page de vente : https://voxia-hub.github.io/CRM/
  - application : https://voxia-hub.github.io/CRM/app.html
- Supabase → Authentication → URL Configuration : Site URL `https://voxia-hub.github.io/CRM/app.html` et Redirect URL `https://voxia-hub.github.io/**` (à vérifier si la connexion ne marche pas).

**La vente**
- 27 prospects listés dans `prospects.csv` (A : marques, B : agences, C : à vérifier).
- Messages personnalisés prêts pour **For.Me, Blissim et Cut by Fred**.
- Méthode complète : séquence de contact sur 10 jours, déroulé de démo, offre, réponses aux objections.

**Présentations** (liens Claude privés, à partager depuis le menu « Partager ») :
- Diapo 15 slides « Créapilot de A à Z » : https://claude.ai/artifact/Ba7SZsm2pDx2LLNez86noe
- Diapo 8 slides « CRM TikTok Shop, le projet » : https://claude.ai/artifact/JkvtCMivwjbNE3z3HtHeUw
- Démo de l’appli (mode démo) : https://claude.ai/artifact/AA4EDttnYrQrwvycjNjxx5
- Page de vente (aperçu) : https://claude.ai/artifact/2TKdzoR9kqoVvufP81bbcf
- Guide de marque : https://claude.ai/artifact/1R15QmiGmAaYSST33AExLs

## Ce qui reste à faire

**Vérifier (30 min)**
- [ ] Confirmer la vraie connexion par e-mail sur https://voxia-hub.github.io/CRM/app.html. Au 22/10, Supabase n’avait encore aucun compte enregistré. Une fois connecté, l’appli affiche « Enregistré en ligne » et les onglets Équipe et Inscrits.
- [ ] Envoyer une fausse inscription depuis la page de vente, et vérifier qu’elle apparaît dans « Inscrits ».
- [ ] Tester une invitation d’équipe avec une deuxième adresse e-mail.
- [ ] Tester l’import d’un vrai export de commandes TikTok Shop.
- [ ] Installer l’appli sur le téléphone.
- [ ] Facultatif : activer l’IA en créant une clé sur console.anthropic.com, avec une limite de dépense. La coller dans Supabase → Edge Functions → Secrets → `ANTHROPIC_API_KEY`. **Ne jamais la donner dans une conversation.**

**Vendre (dès maintenant)**
- [ ] Envoyer les messages à For.Me, Blissim et Cut by Fred, avec le lien de la page de vente.
- [ ] Contacter 5 marques par jour à partir de `prospects.csv`, avec la séquence J1, J2, J5, J10.
- [ ] Objectif : **5 marques fondatrices**.

**Avant le premier paiement**
- [ ] Créer une **micro-entreprise** (guichet unique de l’INPI, gratuit).
- [ ] Créer un **lien de paiement Stripe** (abonnement à 49 €/mois).
- [ ] Ajouter des mentions légales et une politique de confidentialité (RGPD) sur le site.

**Améliorations possibles ensuite** (selon les retours clients)
- La rentabilité par produit.
- Un récap quotidien par e-mail.
- L’envoi automatique des e-mails d’invitation.
- La connexion directe à l’API TikTok Shop.
- Un nom de domaine à soi (par exemple creapilot.fr). « Créapilot » est encore un nom provisoire : vérifier qu’il est disponible (INPI, domaine) avant de l’utiliser.
