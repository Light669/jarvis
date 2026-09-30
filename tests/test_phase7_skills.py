"""Phase 7 : cycle de vie des skills, statistiques, apprentissages, rétrospectives, retour arrière automatique."""
import json

import pytest

from orchestra.models import OWNER, OrchestraError, PermissionDenied, agent_actor, new_id, now_iso
from tests.test_phase3_runtime import use_mock

UPPER = {
    "nom": "mise-en-majuscules",
    "portee": "agent",
    "contenu": "## Quand l'utiliser\nNormaliser des noms d'entreprises.\n## Étapes\n1. Passer le texte en entrée.\n",
    "code": "import sys\nprint(sys.stdin.read().strip().upper())",
    "tests": [{"entree": "acme", "attendu": "ACME"}, {"entree": "btp lyon", "attendu": "BTP LYON"}],
}


@pytest.fixture(autouse=True)
def fast_sandbox(plat):
    plat.cfg.runtime.prefer_docker = False  # le conteneur Docker est testé en phase 3
    plat.alerts.dedup_seconds = 0


def A(org, k):
    return agent_actor(org[k])


def test_skill_lifecycle_test_review_publish(plat, org):
    s = plat.skills.create(A(org, "s1"), UPPER)
    assert s["statut"] == "approuve" and s["version"] == 1
    assert "auto-test" in plat.skills.get(s["id"])["revue"] or "revue" in s["revue"]
    actions = [r["action"] for r in plat.db.query("SELECT action FROM log_index WHERE cible=?", (s["nom"],))]
    assert ["creation", "auto_test_ok", "revue_approuvee", "publication"] == [a for a in actions if a in
                                                                             ("creation", "auto_test_ok", "revue_approuvee", "publication")]
    note = plat.vault_dir / s["vault_path"]
    assert s["vault_path"] == f"Skills/agents/{org['s1']['id']}/mise-en-majuscules.md" and note.exists()
    assert "statut: approuve" in note.read_text(encoding="utf-8")
    assert "mise-en-majuscules" in "\n".join(plat.git.log(s["vault_path"]))


def test_failing_self_test_stays_draft(plat, org):
    bad = dict(UPPER, nom="skill-casse", tests=[{"entree": "a", "attendu": "Z"}])
    s = plat.skills.create(A(org, "s1"), bad)
    assert s["statut"] == "brouillon" and "ÉCHEC" in s["revue"]
    with pytest.raises(PermissionDenied):  # non approuvé : invisible pour les autres
        plat.skills.use(A(org, "s2"), "skill-casse")


def test_unlimited_number_of_skills(plat, org):
    for i in range(30):
        plat.skills.create(A(org, "a1"), {"nom": f"astuce-{i}", "contenu": f"## Quand l'utiliser\nCas numéro {i} de la procédure standard {i * 7}."})
    assert len(plat.skills.list(agent_id=org["a1"]["id"])) >= 30


def test_scopes_by_level(plat, org):
    with pytest.raises(PermissionDenied):
        plat.skills.create(A(org, "a1"), dict(UPPER, nom="apprenti-equipe", portee="equipe"))
    assert plat.db.query("SELECT * FROM log_index WHERE type_evenement='permission_refusee' AND action='skill.create'")
    with pytest.raises(PermissionDenied):
        plat.skills.create(A(org, "s1"), dict(UPPER, nom="salarie-global", portee="global"))
    r = plat.skills.create(A(org, "r1"), dict(UPPER, nom="resp-equipe", portee="equipe"))
    assert r["portee"] == "equipe" and r["equipe_id"] == org["r1"]["id"]
    g = plat.skills.create(A(org, "chef"), dict(UPPER, nom="chef-global", portee="global",
                                                contenu="## Quand l'utiliser\nProcédure globale de nommage des fichiers clients."))
    assert g["portee"] == "global" and g["vault_path"].startswith("Skills/globaux/")


def test_team_scope_via_formal_request_then_reuse(plat, org):
    s = plat.skills.create(A(org, "s1"), dict(UPPER, portee="equipe"))
    assert s["portee"] == "agent"  # en attendant l'accord du responsable
    req = plat.messaging.pending(org["r1"]["id"])[0]
    assert req["type"] == "skill_equipe"
    with pytest.raises(PermissionDenied):
        plat.skills.use(A(org, "s2"), s["nom"])
    plat.messaging.decide(A(org, "r1"), req["id"], True, "Bonne idée")
    s = plat.skills.get(s["id"])
    assert s["portee"] == "equipe" and s["vault_path"].startswith(f"Skills/equipes/{org['r1']['id']}/")
    assert not (plat.vault_dir / f"Skills/agents/{org['s1']['id']}/mise-en-majuscules.md").exists()
    # réutilisation par un autre agent de l'équipe, via la boucle d'outils
    replies = iter([json.dumps({"actions": [{"outil": "utiliser_skill", "args": {"nom": s["nom"], "entree": "dupont sa"}}]}),
                    '{"final": "DUPONT SA", "apprentissage": "le skill de majuscules marche bien"}'])
    prov = use_mock(plat, org["s2"]["id"], lambda m, msgs: next(replies))
    t = plat.runtime.assign(OWNER, org["s2"]["id"], "Normalise le nom dupont sa", background=False)
    assert "DUPONT SA" in prov.calls[-1][1][-1]["content"]
    plat.runtime.validate(OWNER, t["id"], True)
    stats = plat.skills.get(s["id"])
    assert stats["utilisations"] == 1 and stats["evaluations"] == 1 and stats["taux_reussite"] == 1.0
    # hors équipe : refusé
    with pytest.raises(PermissionDenied):
        plat.skills.use(A(org, "s3"), s["nom"])


def test_skill_never_grants_rights_nor_contains_secrets(plat, org):
    with pytest.raises(PermissionDenied):
        plat.skills.create(A(org, "s2"), dict(UPPER, nom="web", permissions_requises=["recherche_web"]))
    with pytest.raises(OrchestraError):
        plat.skills.create(A(org, "s1"), dict(UPPER, nom="fuite", contenu="Utiliser la clé gsk_ABCDEFGHIJKLMNOPQRSTUV123"))
    assert plat.db.query("SELECT * FROM alerts WHERE type='secret_skill'")
    # un skill qui requiert un outil ne s'exécute que pour qui détient cet outil
    s = plat.skills.create(A(org, "s1"), dict(UPPER, nom="avec-web", portee="agent", permissions_requises=["recherche_web"]))
    assert s["statut"] == "approuve"
    plat.agents.update(OWNER, org["s1"]["id"], {"outils": []})
    with pytest.raises(PermissionDenied):
        plat.skills.use(A(org, "s1"), "avec-web")


def test_dangerous_code_rejected_by_verifier(plat, org):
    s = plat.skills.create(A(org, "s1"), dict(UPPER, nom="reseau", code="import urllib.request, sys\nprint(sys.stdin.read().upper())"))
    assert s["statut"] == "brouillon" and "réseau" in s["revue"]


def test_discovery_injects_relevant_skills_in_prompt(plat, org):
    plat.skills.create(A(org, "chef"), {"nom": "relance-prospect", "portee": "global",
                                        "contenu": "## Quand l'utiliser\nRelancer un prospect B2B après un premier contact sans réponse.\n## Étapes\n1. Attendre 5 jours."})
    prov = use_mock(plat, org["s2"]["id"], lambda m, msgs: '{"final": "ok"}')
    plat.runtime.assign(OWNER, org["s2"]["id"], "Prépare la relance du prospect Dupont", background=False)
    system = prov.calls[-1][1][0]["content"]
    assert "Skill « relance-prospect »" in system


def test_learning_note_and_journal_after_task(plat, org):
    use_mock(plat, org["s1"]["id"], lambda m, msgs: '{"final": "fait", "apprentissage": "Vérifier le SIREN évite les doublons"}')
    v = plat.agents.get(org["s1"]["id"])["version"]
    plat.runtime.assign(OWNER, org["s1"]["id"], "Qualifie 3 prospects", background=False)
    l = plat.db.one("SELECT * FROM learnings WHERE agent_id=?", (org["s1"]["id"],))
    assert "SIREN" in l["texte"] and (plat.vault_dir / l["vault_path"]).exists()
    a = plat.agents.get(org["s1"]["id"])
    assert "SIREN" in a["journal"] and a["version"] == v  # le journal ne crée pas de version
    assert "SIREN" in (plat.vault_dir / a["vault_path"]).read_text(encoding="utf-8")


def _fake_tasks(plat, agent_id, version, results, point=None):
    ids = []
    for ok in results:
        tid = new_id("tache")
        plat.db.execute("INSERT INTO tasks(id,agent_id,agent_version,consigne,statut,debut,fin,correlation_id) VALUES(?,?,?,?,?,?,?,?)",
                        (tid, agent_id, version, "tâche simulée", "terminee", now_iso(), now_iso(), new_id("corr")))
        plat.runtime.validate(OWNER, tid, ok, None if ok else point)
        ids.append(tid)
    return ids


def test_automatic_rollback_on_degradation(plat, org):
    sid = org["s1"]["id"]
    _fake_tasks(plat, sid, 1, [True] * 5)
    a = plat.agents.update(A(org, "s1"), sid, {"instructions": "Nouvelle méthode risquée"}, "auto-amélioration")
    assert a["version"] == 2
    _fake_tasks(plat, sid, 2, [False] * 5)
    a = plat.agents.get(sid)
    assert a["instructions"] == "" and a["version"] == 3  # contenu de la v1 restauré dans une nouvelle version
    assert plat.db.query("SELECT * FROM log_index WHERE action='retour_arriere' AND cible=?", (sid,))
    assert plat.db.query("SELECT * FROM alerts WHERE type='retour_arriere'")
    assert list((plat.vault_dir / "Decisions").glob("*retour-arriere*"))


def test_no_rollback_when_results_hold(plat, org):
    sid = org["s1"]["id"]
    _fake_tasks(plat, sid, 1, [True, True, False, True, True])  # 80 %
    plat.agents.update(OWNER, sid, {"instructions": "Meilleure méthode"})
    _fake_tasks(plat, sid, 2, [True, True, True, True, False])  # 80 % : pas de dégradation
    assert plat.agents.get(sid)["instructions"] == "Meilleure méthode"


def test_skill_rollback_on_degradation(plat, org):
    s = plat.skills.create(A(org, "s1"), UPPER)
    for ok in [True] * 5:
        t = _fake_tasks(plat, org["s1"]["id"], 1, [])  # noqa
        tid = new_id("tache")
        plat.db.execute("INSERT INTO tasks(id,agent_id,agent_version,consigne,statut,debut,fin,skills_utilises) VALUES(?,?,?,?,?,?,?,?)",
                        (tid, org["s1"]["id"], 1, "x", "terminee", now_iso(), now_iso(), json.dumps([s["id"]])))
        plat.skills.use(A(org, "s1"), s["nom"], "a", task_id=tid)
        plat.runtime.validate(OWNER, tid, ok)
    plat.skills.update(A(org, "s1"), s["id"], {"contenu": UPPER["contenu"] + "\nVersion 2 moins bonne."})
    assert plat.skills.get(s["id"])["version"] == 2
    for ok in [False] * 5:
        tid = new_id("tache")
        plat.db.execute("INSERT INTO tasks(id,agent_id,agent_version,consigne,statut,debut,fin,skills_utilises) VALUES(?,?,?,?,?,?,?,?)",
                        (tid, org["s1"]["id"], 1, "x", "terminee", now_iso(), now_iso(), json.dumps([s["id"]])))
        plat.skills.use(A(org, "s1"), s["nom"], "a", task_id=tid)
        plat.runtime.validate(OWNER, tid, ok)
    s2 = plat.skills.get(s["id"])
    assert s2["version"] == 3 and "Version 2 moins bonne" not in s2["contenu"]
    assert plat.db.query("SELECT * FROM log_index WHERE action='retour_arriere_skill'")


def test_promotion_eligibility_signalled(plat, org):
    plat.cfg.hierarchy.promotion.min_validated_tasks = 20
    _fake_tasks(plat, org["a1"]["id"], 1, [True] * 18 + [False, True])
    assert plat.db.query("SELECT * FROM alerts WHERE type='promotion_eligible'")
    msgs = plat.db.query("SELECT * FROM messages WHERE a=? AND sujet LIKE 'Promotion possible%'", (org["r1"]["id"],))
    assert msgs
    assert plat.agents.get(org["a1"]["id"])["niveau"] == "apprenti"  # pas de promotion automatique : le Chef valide


def test_repeated_failures_after_correction(plat, org):
    sid = org["s2"]["id"]
    _fake_tasks(plat, sid, 1, [False], point="format du devis")
    plat.agents.update(OWNER, sid, {"instructions": "Utiliser le modèle de devis"})
    _fake_tasks(plat, sid, 2, [False], point="Format du devis")
    assert plat.db.query("SELECT * FROM alerts WHERE type='echecs_repetes'")
    assert plat.db.query("SELECT * FROM messages WHERE a=? AND sujet LIKE 'Échecs répétés%'", (org["chef"]["id"],))


def test_daily_and_weekly_reports(plat, org):
    s1 = plat.skills.create(A(org, "s1"), {"nom": "doublon-a", "contenu": "## Quand l'utiliser\nRelancer les prospects froids par courriel après une semaine sans réponse."})
    for i in range(3):
        plat.db.execute("INSERT INTO learnings(agent_id,task_id,succes,texte,horodatage) VALUES(?,?,?,?,?)",
                        (org["s1"]["id"], f"t{i}", 1, "La vérification SIREN évite les doublons", now_iso()))
    rel = plat.improvement.daily()
    text = (plat.vault_dir / rel).read_text(encoding="utf-8")
    assert "siren" in text.lower() and "proposition" in text
    _fake_tasks(plat, org["s1"]["id"], 1, [True] * 4)
    _fake_tasks(plat, org["s3"]["id"], 1, [False] * 3)
    rel = plat.improvement.weekly()
    text = (plat.vault_dir / rel).read_text(encoding="utf-8")
    assert "**garder**" in text and "**retirer**" in text
    decisions = list((plat.vault_dir / "Decisions").glob("*retrospective-hebdomadaire*"))
    assert decisions
    assert plat.agents.get(org["s3"]["id"])["statut"] == "actif"  # « retirer » reste une proposition
    assert s1


def test_obsolete_never_deleted(plat, org):
    s = plat.skills.create(A(org, "s1"), UPPER)
    s = plat.skills.obsolete(A(org, "s1"), s["id"], "remplacé")
    assert s["statut"] == "obsolete" and s["vault_path"].startswith("Archives/Skills/")
    assert (plat.vault_dir / s["vault_path"]).exists()
    assert plat.db.one("SELECT * FROM skills WHERE id=?", (s["id"],))


def test_owner_edits_skill_in_obsidian(plat, org):
    s = plat.skills.create(A(org, "s1"), UPPER)
    path = plat.vault_dir / s["vault_path"]
    path.write_text(path.read_text(encoding="utf-8").replace("Normaliser des noms", "Normaliser les raisons sociales"), encoding="utf-8")
    assert plat.scribe.import_note(s["vault_path"]) == "skill_modifie"
    s2 = plat.skills.get(s["id"])
    assert "raisons sociales" in s2["contenu"] and s2["version"] == 2


def test_agent_creates_skill_through_tool(plat, org):
    replies = iter([json.dumps({"actions": [{"outil": "creer_skill", "args": UPPER}]}), '{"final": "skill créé"}'])
    prov = use_mock(plat, org["s1"]["id"], lambda m, msgs: next(replies))
    plat.runtime.assign(OWNER, org["s1"]["id"], "Crée un skill de majuscules", background=False)
    assert "statut approuve" in prov.calls[-1][1][-1]["content"]


def test_api_skills(plat, org):
    from fastapi.testclient import TestClient
    from orchestra.api.app import create_app
    H = {"Authorization": "Bearer test-token-0123456789"}
    s = plat.skills.create(A(org, "s1"), UPPER)
    with TestClient(create_app(platform=plat, background=False)) as c:
        rows = c.get("/api/skills", headers=H).json()
        assert rows[0]["nom"] == "mise-en-majuscules" and "taux_reussite" in rows[0]
        assert c.get(f"/api/skills?agent_id={org['s1']['id']}", headers=H).json()
        assert c.get(f"/api/skills/{s['id']}", headers=H).json()["versions"]
        assert c.post("/api/improvement/weekly", headers=H).json()["rapport"].startswith("Rapports/")
        assert c.post(f"/api/skills/{s['id']}/obsolete", json={"raison": "test"}, headers=H).json()["statut"] == "obsolete"
