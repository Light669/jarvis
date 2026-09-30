"""Organisation de démonstration (python -m orchestra demo) : Chef, 2 équipes, messages, une demande.

Les agents utilisent le modèle hors ligne `demo/echo` : aucune clé ni Ollama nécessaire.
Changez leur modèle dans la fiche pour passer à un vrai modèle.
"""
from __future__ import annotations

from orchestra.models import OWNER, agent_actor


def seed(p) -> dict[str, dict]:
    if p.agents.list():
        raise SystemExit("La base contient déjà des agents : démonstration non créée.")
    A = p.agents
    m = "demo/echo"
    chef = A.create(OWNER, {"nom": "Chef d'Orchestre", "niveau": "chef", "statut": "actif", "modele": m, "budget_jour_eur": 1.0,
                            "role": "Diriger l'entreprise, répartir le budget, arbitrer les demandes.",
                            "objectif": "Atteindre les objectifs mensuels dans le budget de 100 €."})
    ventes = A.create(OWNER, {"nom": "Responsable Ventes", "niveau": "responsable", "parent_id": chef["id"], "statut": "actif", "modele": m,
                              "budget_mois_eur": 30, "role": "Piloter la prospection et la conversion."})
    contenu = A.create(OWNER, {"nom": "Responsable Contenu", "niveau": "responsable", "parent_id": chef["id"], "statut": "actif", "modele": m,
                               "budget_mois_eur": 30, "role": "Produire les contenus courts (TikTok, Reels, Shorts)."})
    prosp = A.create(OWNER, {"nom": "Prospecteur", "niveau": "salarie", "parent_id": ventes["id"], "statut": "actif", "modele": m,
                             "outils": ["recherche_web"], "role": "Trouver et qualifier des prospects B2B.",
                             "instructions": "Toujours vérifier le SIREN. Jamais de démarchage sans accord.", "kpi": ["10 leads/semaine"]})
    redac = A.create(OWNER, {"nom": "Rédacteur", "niveau": "salarie", "parent_id": ventes["id"], "statut": "actif", "modele": m,
                             "role": "Rédiger les e-mails de relance (brouillons uniquement)."})
    monteur = A.create(OWNER, {"nom": "Monteur", "niveau": "salarie", "parent_id": contenu["id"], "statut": "actif", "modele": m,
                               "role": "Monter les vidéos verticales."})
    appr = A.create(OWNER, {"nom": "Apprenti Ventes", "niveau": "apprenti", "parent_id": prosp["id"], "statut": "actif", "modele": m,
                            "role": "Préparer des listes de prospects sous supervision."})
    A.create(OWNER, {"nom": "Apprenti Montage", "niveau": "apprenti", "parent_id": monteur["id"], "statut": "brouillon", "modele": m})
    msg = p.messaging
    t = msg.send(agent_actor(prosp), redac["id"], "Liste de prospects prête", "10 PME du BTP à Lyon, prêtes pour la relance.")
    msg.send(agent_actor(redac), prosp["id"], "Re: Liste de prospects prête", "Merci, je prépare les brouillons.", thread_id=t["thread_id"])
    msg.send(agent_actor(appr), prosp["id"], "Question", "Faut-il inclure les auto-entrepreneurs ?")
    msg.request(agent_actor(redac), "acces_outil", "Accès à la recherche web", "Vérifier les sites des prospects avant relance",
                "Relances plus pertinentes", 0, payload={"outil": "recherche_web"})
    return {"chef": chef, "ventes": ventes, "contenu": contenu, "prospecteur": prosp}
