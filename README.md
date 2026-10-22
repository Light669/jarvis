# Créapilot

MVP d’un CRM pour les vendeurs **TikTok Shop** : suivre ses créateurs affiliés, de la prise de contact jusqu’aux ventes.

> « Créapilot » est un nom provisoire.

*Pilote tes créateurs, pas ton tableur.* Le guide de marque (logo, couleurs, typographie, ton) est dans `brand.html`.

## Ce que fait le MVP

- **Tableau de bord** : ventes et commissions des 30 derniers jours (avec évolution), créateurs qui ont posté, retour sur échantillons, ventes par semaine (graphique ou tableau), liste « À faire aujourd’hui », parcours des créateurs étape par étape et classement des meilleurs créateurs.
- **Ventes par créateur** : chaque vente est enregistrée avec sa date ; la commission due se calcule toute seule.
- **Tableau en colonnes** : Trouvés → Contactés → Échantillon envoyé → Vidéo postée → Génère des ventes. On déplace les cartes par glisser-déposer ou avec le bouton « Suivant ».
- **Relances automatiques** : un créateur trouvé depuis 5 jours, contacté depuis 3 jours sans suite, ou qui a reçu un échantillon depuis 7 jours sans vidéo apparaît dans « À faire aujourd’hui ».
- **Messages prêts à copier** : invitation, relance, brief vidéo et remerciement, personnalisés avec le pseudo, le produit, la commission, la marque et le prénom.
- **Chiffres clés** : créateurs suivis, échantillons sans vidéo, ventes générées et commissions à verser.
- **Import et export** : coller une liste depuis Excel ou Google Sheets (ou déposer un CSV), et copier toute la liste pour la recoller dans un tableur.
- **Filtres** : catégorie, produit, « à relancer seulement ».
- **Historique** par créateur, bouton « J’ai envoyé ce message » et annulation de la dernière action.
- **Fiche créateur** : catégorie, abonnés, commission, produit, ventes, notes.

## Lancer l’application

Aucune installation : ouvrir `index.html` dans un navigateur.

Pour la mettre en ligne gratuitement : activer **GitHub Pages** sur ce dépôt (Settings → Pages → branche `main`, dossier `/`), ou glisser le dossier sur Netlify Drop.

## Comptes et sauvegarde en ligne

Sans configuration, l’application tourne en mode démo (données dans le navigateur). Pour activer la connexion par e-mail et la sauvegarde en ligne avec Supabase, suis [SUPABASE.md](SUPABASE.md).

## Limites connues (volontaires pour un MVP)

- Un espace par compte : pas encore de partage entre plusieurs membres d’une équipe.
- Les messages viennent de modèles de texte, pas encore d’une IA.
- Pas de connexion à TikTok Shop : les ventes se saisissent à la main.

## Prochaines étapes

1. Montrer le MVP à 20 vendeurs ou agences TikTok Shop et noter leurs retours.
2. Obtenir 5 à 10 préventes (tarif fondateur).
3. Créer le projet Supabase et activer les comptes (voir SUPABASE.md).
4. Brancher l’IA (Claude) pour rédiger les messages et suggérer des créateurs.
5. Étudier l’API Partenaires de TikTok Shop pour importer les ventes automatiquement.
