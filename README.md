# Créapilot

MVP d’un CRM pour les vendeurs **TikTok Shop** : suivre ses créateurs affiliés, de la prise de contact jusqu’aux ventes.

> « Créapilot » est un nom provisoire.

*Pilote tes créateurs, pas ton tableur.*

| Fichier | Rôle |
|---|---|
| `index.html` | Page de vente, avec le formulaire « Réserver ma place fondateur » |
| `app.html` | L’application Créapilot |
| `brand.html` | Guide de marque (logo, couleurs, typographie, ton) |
| `config.js` | Clés Supabase partagées par la page de vente et l’application |
| `supabase/` | Schéma de la base et fonction serveur de rédaction par IA |

## Ce que fait le MVP

- **Bien démarrer** : pour un nouvel espace, une liste de 5 étapes qui se cochent toutes seules (infos, créateurs, stock, premier message, première vente).
- **Tableau de bord** : ventes et commissions des 30 derniers jours (avec évolution), créateurs qui ont posté, retour sur échantillons, ventes par semaine (graphique ou tableau), liste « À faire aujourd’hui », parcours des créateurs étape par étape et classement des meilleurs créateurs.
- **Ventes par créateur** : chaque vente est enregistrée avec sa date ; la commission due se calcule toute seule.
- **Tableau en colonnes** : Trouvés → Contactés → Échantillon envoyé → Vidéo postée → Génère des ventes. On déplace les cartes par glisser-déposer ou avec le bouton « Suivant ».
- **Relances automatiques** : un créateur trouvé depuis 5 jours, contacté depuis 3 jours sans suite, ou qui a reçu un échantillon depuis 7 jours sans vidéo apparaît dans « À faire aujourd’hui ».
- **Messages prêts à copier** : invitation, relance, brief vidéo et remerciement, personnalisés avec le pseudo, le produit, la commission, la marque et le prénom.
- **Rédaction par IA** (version en ligne) : Claude écrit un message sur mesure à partir de la fiche du créateur, avec une consigne facultative. La clé d’API reste côté serveur (fonction Supabase `generate-message`).
- **Chiffres clés** : créateurs suivis, échantillons sans vidéo, ventes générées et commissions à verser.
- **Import et export** : coller une liste depuis Excel ou Google Sheets (ou déposer un CSV), et copier toute la liste pour la recoller dans un tableur.
- **Filtres** : catégorie, produit, « à relancer seulement ».
- **Historique** par créateur, bouton « J’ai envoyé ce message » et annulation de la dernière action.
- **Colis d’échantillons** : adresse, transporteur, numéro de suivi cliquable, dates d’envoi et de livraison, vue « À envoyer / En route / Livrés », stock d’échantillons par produit (baisse automatique à chaque envoi). L’alerte « Vidéo en retard » part de la date de livraison réelle.
- **Inscrits** (compte administrateur) : la liste des marques inscrites depuis la page de vente.
- **Fiche créateur** : catégorie, abonnés, commission, produit, ventes, notes.

## Lancer l’application

Aucune installation : ouvrir `index.html` (page de vente) ou `app.html` (application) dans un navigateur.

Pour la mettre en ligne gratuitement : activer **GitHub Pages** sur ce dépôt (Settings → Pages → branche `main`, dossier `/`), ou glisser le dossier sur Netlify Drop.

## Comptes et sauvegarde en ligne

Sans configuration, l’application tourne en mode démo (données dans le navigateur). Pour activer la connexion par e-mail et la sauvegarde en ligne avec Supabase, suis [SUPABASE.md](SUPABASE.md).

## Limites connues (volontaires pour un MVP)

- Un espace par compte : pas encore de partage entre plusieurs membres d’une équipe.
- La rédaction par IA demande la version en ligne (Supabase) et une clé d’API Anthropic.
- Pas de connexion à TikTok Shop : les ventes se saisissent à la main.

## Prochaines étapes

1. Montrer le MVP à 20 vendeurs ou agences TikTok Shop et noter leurs retours.
2. Obtenir 5 à 10 préventes (tarif fondateur).
3. Créer le projet Supabase et activer les comptes (voir SUPABASE.md).
4. Déployer la fonction de rédaction par IA (voir SUPABASE.md, section 6).
5. Étudier l’API Partenaires de TikTok Shop pour importer les ventes automatiquement.
