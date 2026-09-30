"""Phase 5 : Scribe — synchronisation bidirectionnelle base ⇄ Obsidian, Git, index plein texte."""
import subprocess
import time

import pytest
import yaml

from orchestra.models import OWNER, PermissionDenied, agent_actor
from orchestra.scribe.writer import parse_note


def read(plat, rel):
    return parse_note((plat.vault_dir / rel).read_text(encoding="utf-8"))


def git_log(plat):
    plat.git.flush()
    return subprocess.run(["git", "log", "--pretty=%s%n%b"], cwd=plat.vault_dir, capture_output=True, text=True).stdout


def test_agent_note_written_on_create(plat, org):
    s1 = org["s1"]
    assert s1["vault_path"] == "Agents/Salaries/prospecteur.md"
    fm, body = read(plat, s1["vault_path"])
    assert fm["id"] == s1["id"] and fm["niveau"] == "salarie" and fm["superieur"] == org["r1"]["id"]
    assert fm["outils"] == ["recherche_web"] and fm["version"] == 1
    for title in ("## Rôle", "## Contexte", "## Instructions", "## Objectif et KPI", "## Interdits", "## Journal de bord"):
        assert title in body
    assert "[[resp-ventes|Resp Ventes]]" in body  # lien vers le supérieur (graphe Obsidian)
    parent_fm, parent_body = read(plat, org["r1"]["vault_path"])
    assert "[[prospecteur|Prospecteur]]" in parent_body  # subordonnés listés
    assert "Création de la fiche Prospecteur" in git_log(plat)


def test_form_edit_updates_note_and_git(plat, org):
    a = plat.agents.update(OWNER, org["s1"]["id"], {"contexte": "Marché des PME", "instructions": "Cibler Lyon"})
    fm, body = read(plat, a["vault_path"])
    assert fm["version"] == 2 and "Cibler Lyon" in body and "Marché des PME" in body
    assert "v2 par proprietaire" in git_log(plat)


def test_manual_obsidian_edit_applied_owner_wins(plat, org):
    rel = org["s1"]["vault_path"]
    path = plat.vault_dir / rel
    text = path.read_text(encoding="utf-8").replace("## Instructions\n", "## Instructions\nAppeler avant 10 h.\n")
    path.write_text(text, encoding="utf-8")
    assert plat.scribe.import_note(rel) == "agent_modifie"
    a = plat.agents.get(org["s1"]["id"])
    assert a["instructions"] == "Appeler avant 10 h." and a["version"] == 2
    assert plat.scribe.import_note(rel) == "inchangee"  # anti-écho : pas de boucle
    log = plat.db.query("SELECT * FROM log_index WHERE action='modification_fiche' AND cible=?", (a["id"],))[-1]
    assert log["agent_id"] == "proprietaire"
    # l'ancienne version reste dans l'historique Git
    plat.git.flush()
    old = subprocess.run(["git", "log", "--pretty=%H", "--", rel], cwd=plat.vault_dir, capture_output=True, text=True).stdout.split()
    assert len(old) >= 2
    first = subprocess.run(["git", "show", f"{old[-1]}:{rel}"], cwd=plat.vault_dir, capture_output=True, text=True).stdout
    assert "Appeler avant 10 h." not in first


def test_create_agent_from_note(plat, org):
    tpl = (plat.vault_dir / "Modeles_de_notes/agent.md").read_text(encoding="utf-8")
    fm, body = parse_note(tpl)
    fm.update({"nom": "Marie Analyste", "niveau": "salarie", "superieur": org["r2"]["id"], "statut": "actif", "kpi": ["5 analyses/sem"]})
    body = body.replace("## Instructions\n", "## Instructions\nAnalyser les tendances.\n")
    rel = "Agents/Salaries/marie-analyste.md"
    (plat.vault_dir / rel).write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n" + body, encoding="utf-8")
    assert plat.scribe.import_note(rel) == "agent_cree"
    a = plat.agents.find("Marie Analyste")
    assert a and a["parent_id"] == org["r2"]["id"] and a["instructions"] == "Analyser les tendances."
    assert a["vault_path"] == rel and a["kpi"] == ["5 analyses/sem"] and a["cree_par"] == "proprietaire"
    fm2, _ = read(plat, rel)
    assert fm2["id"] == a["id"]  # l'identifiant attribué est réécrit dans la note


def test_invalid_note_is_refused_with_alert(plat, org):
    rel = org["s2"]["vault_path"]
    path = plat.vault_dir / rel
    path.write_text(path.read_text(encoding="utf-8").replace("niveau: salarie", "niveau: directeur"), encoding="utf-8")
    assert plat.scribe.import_note(rel).startswith("erreur")
    assert plat.agents.get(org["s2"]["id"])["niveau"] == "salarie"
    assert plat.db.query("SELECT * FROM alerts WHERE type='import_obsidian'")


def test_deleted_note_is_restored(plat, org):
    rel = org["s2"]["vault_path"]
    (plat.vault_dir / rel).unlink()
    assert plat.scribe.import_note(rel) == "restauree"
    assert (plat.vault_dir / rel).exists()


def test_promotion_and_archive_move_notes(plat, org):
    a = plat.agents.promote(OWNER, org["a1"]["id"])
    assert (plat.vault_dir / a["vault_path"]).exists() and a["vault_path"].startswith("Agents/Salaries/")
    assert not (plat.vault_dir / org["a1"]["vault_path"]).exists()
    a2 = plat.agents.set_status(OWNER, org["a2"]["id"], "archive", "remplacé")
    a2 = plat.agents.get(a2["id"])
    assert a2["vault_path"].startswith("Archives/Agents/") and (plat.vault_dir / a2["vault_path"]).exists()


def test_agent_writes_only_in_own_folder(plat, org):
    a1 = agent_actor(org["a1"])
    path = plat.scribe.write_agent_note(a1, "brouillon.md", "# Mes notes")
    assert path == "Agents/Apprentis/apprenti-ventes/brouillon.md"
    for bad in ["Agents/Chef/chef.md", "Skills/globaux/pirate.md", "Agents/Apprentis/apprenti-contenu/x.md", "../evil.md"]:
        with pytest.raises(PermissionDenied):
            plat.scribe.write_as(a1, bad, "x")
    refus = plat.db.query("SELECT * FROM log_index WHERE type_evenement='permission_refusee' AND action='vault.write'")
    assert len(refus) == 4


def test_read_perimeter(plat, org):
    plat.scribe.write_agent_note(agent_actor(org["a2"]), "secret-equipe.md", "contenu")
    with pytest.raises(PermissionDenied):
        plat.scribe.read_as(agent_actor(org["s1"]), "Agents/Apprentis/apprenti-contenu/secret-equipe.md")
    assert plat.scribe.read_as(agent_actor(org["r2"]), "Agents/Apprentis/apprenti-contenu/secret-equipe.md") == "contenu\n"
    assert plat.scribe.read_as(agent_actor(org["chef"]), "Agents/Apprentis/apprenti-contenu/secret-equipe.md")


def test_full_text_search(plat, org):
    plat.agents.update(OWNER, org["s3"]["id"], {"instructions": "Montage vidéo vertical avec sous-titres dynamiques"})
    hits = plat.scribe.search("sous-titres dynamiques")
    assert hits and hits[0]["path"] == org["s3"]["vault_path"] and "**" in hits[0]["extrait"]
    # un salarié d'une autre équipe ne voit pas la fiche
    assert not plat.scribe.search("sous-titres dynamiques", actor=agent_actor(org["s1"]))
    assert plat.scribe.reindex() > 5


def test_daily_readable_log(plat, org):
    files = list((plat.vault_dir / "Logs").glob("*.md"))
    assert files
    text = files[0].read_text(encoding="utf-8")
    assert "# Journal du" in text and "creation" in text


def test_watcher_applies_manual_edit(plat, org):
    plat.scribe.start()
    try:
        rel = org["s2"]["vault_path"]
        path = plat.vault_dir / rel
        time.sleep(0.3)
        path.write_text(path.read_text(encoding="utf-8").replace("## Contexte\n", "## Contexte\nÉdité dans Obsidian\n"), encoding="utf-8")
        for _ in range(50):
            if plat.agents.get(org["s2"]["id"])["contexte"] == "Édité dans Obsidian":
                break
            time.sleep(0.1)
        assert plat.agents.get(org["s2"]["id"])["contexte"] == "Édité dans Obsidian"
        # création d'un agent par une nouvelle note, détectée automatiquement
        (plat.vault_dir / "Agents/Apprentis/leo.md").write_text(
            f"---\nnom: Léo\nniveau: apprenti\nsuperieur: {org['s2']['id']}\nstatut: actif\n---\n# Léo\n## Rôle\nStagiaire\n", encoding="utf-8")
        for _ in range(50):
            if plat.agents.find("Léo"):
                break
            time.sleep(0.1)
        leo = plat.agents.find("Léo")
        assert leo and leo["role"] == "Stagiaire"
    finally:
        plat.scribe.stop()


def test_api_search_and_history(plat, org):
    from fastapi.testclient import TestClient
    from orchestra.api.app import create_app
    H = {"Authorization": "Bearer test-token-0123456789"}
    plat.agents.update(OWNER, org["s1"]["id"], {"contexte": "prospection immobilière"})
    with TestClient(create_app(platform=plat, background=False)) as c:
        assert c.get("/api/search", params={"q": "immobilière"}, headers=H).json()
        h = c.get(f"/api/agents/{org['s1']['id']}/history", headers=H).json()
        assert len(h["commits"]) >= 2 and len(h["versions"]) == 2
        note = c.get("/api/vault/note", params={"path": org["s1"]["vault_path"]}, headers=H).json()
        assert "prospection immobilière" in note["contenu"]
