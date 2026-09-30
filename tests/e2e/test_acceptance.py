"""Recette : un test par critère d'acceptation du §14 du cahier des charges.

Ce qui ne peut être prouvé que sous Windows (toasts, start.ps1, Docker Desktop, Ollama GPU) est listé
dans docs/avancement.md, section « À valider par le Propriétaire ».
"""
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from orchestra.api.app import create_app
from orchestra.models import OWNER, BudgetExceeded, PermissionDenied, RateLimited, agent_actor, new_id, now, now_iso
from orchestra.redact import scan_paths
from tests.test_phase3_runtime import use_mock

REPO = Path(__file__).resolve().parents[2]
H = {"Authorization": "Bearer test-token-0123456789"}


@pytest.fixture()
def api(plat):
    plat.cfg.runtime.prefer_docker = False
    plat.alerts.dedup_seconds = 0
    with TestClient(create_app(platform=plat, background=False)) as c:
        yield c


def A(org, k):
    return agent_actor(org[k])


# 1 --------------------------------------------------------------------------------------------
def test_01_start_and_stop_in_one_command(tmp_path):
    """start.sh lance tout (coffre, base, API, notifier) ; stop.sh arrête tout proprement.
    (start.ps1 / stop.ps1 suivent exactement les mêmes étapes sous Windows.)"""
    root = tmp_path / "Orchestra"
    root.mkdir()
    for f in ["config.yaml", ".env.example", "start.sh", "stop.sh", "docker-compose.yml"]:
        shutil.copy2(REPO / f, root / f)
    shutil.copytree(REPO / "platform", root / "platform", ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    cfg["server"]["port"] = port
    (root / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    env = {**os.environ, "PYTHON": "python3"}
    env.pop("ORCHESTRA_TOKEN", None)
    r = subprocess.run(["bash", "start.sh"], cwd=root, capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Orchestra est lancé" in r.stdout
    token = [l for l in (root / ".env").read_text().splitlines() if l.startswith("ORCHESTRA_TOKEN=")][0].split("=", 1)[1]
    assert len(token) == 64
    import httpx
    assert httpx.get(f"http://127.0.0.1:{port}/api/health").json()["ok"]
    assert httpx.get(f"http://127.0.0.1:{port}/api/agents").status_code == 401
    assert httpx.get(f"http://127.0.0.1:{port}/api/agents", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert (root / "Cerveau" / "00_Accueil.md").exists() and (root / "data" / "orchestra.db").exists()
    pid = int((root / "data" / "orchestra.pid").read_text())
    r = subprocess.run(["bash", "stop.sh"], cwd=root, capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0 and "arrêté" in r.stdout
    time.sleep(0.5)
    with pytest.raises(httpx.HTTPError):
        httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2)
    status = Path(f"/proc/{pid}/status")
    assert not status.exists() or "zombie" in status.read_text()  # arrêté (éventuellement pas encore récolté)
    logs = "".join(f.read_text(encoding="utf-8") for f in (root / "logs").glob("*.jsonl"))
    assert "demarrage_api" in logs and "arret_demande" in logs


# 2 --------------------------------------------------------------------------------------------
def test_02_create_agent_from_form_and_from_obsidian_note(plat, org, api):
    a = api.post("/api/agents", json={"nom": "Veilleur", "niveau": "salarie", "parent_id": org["r2"]["id"],
                                      "instructions": "Surveiller les tendances"}, headers=H).json()
    assert (plat.vault_dir / a["vault_path"]).exists()
    rel = "Agents/Salaries/graphiste.md"
    (plat.vault_dir / rel).write_text(f"---\nnom: Graphiste\nniveau: salarie\nsuperieur: {org['r2']['id']}\nstatut: actif\n---\n"
                                      "# Graphiste\n## Rôle\nMiniatures YouTube\n", encoding="utf-8")
    assert plat.scribe.import_note(rel) == "agent_cree"
    carte = {x["nom"] for x in api.get("/api/overview", headers=H).json()["agents"]}
    assert {"Veilleur", "Graphiste"} <= carte


# 3 --------------------------------------------------------------------------------------------
def test_03_edit_context_and_instructions(plat, org, api):
    sid = org["s1"]["id"]
    prov = use_mock(plat, sid, lambda m, msgs: '{"final": "ok"}')
    r = api.patch(f"/api/agents/{sid}", json={"contexte": "Clients : PME lyonnaises", "instructions": "Toujours vouvoyer"}, headers=H).json()
    assert r["version"] == 2
    assert any("v2" in c for c in plat.git.log(r["vault_path"]))
    log = plat.db.query("SELECT ligne FROM log_index WHERE action='modification_fiche' AND cible=?", (sid,))[-1]
    assert json.loads(log["ligne"])["details"]["apres"]["instructions"] == "Toujours vouvoyer"
    t = plat.runtime.assign(OWNER, sid, "Rédige une relance", background=False)
    assert t["agent_version"] == 2
    system = prov.calls[-1][1][0]["content"]
    assert "Toujours vouvoyer" in system and "PME lyonnaises" in system


# 4 --------------------------------------------------------------------------------------------
def test_04_apprentice_refused_other_level_and_outside_folder(plat, org):
    a1 = A(org, "a1")
    with pytest.raises(PermissionDenied):
        plat.messaging.send(a1, org["r1"]["id"], "Salut", "Je veux parler au responsable")
    with pytest.raises(PermissionDenied):
        plat.scribe.write_as(a1, "Agents/Salaries/prospecteur/piratage.md", "x")
    refus = plat.db.query("SELECT action FROM log_index WHERE type_evenement='permission_refusee' AND agent_id=?", (org["a1"]["id"],))
    assert {"message.send", "vault.write"} <= {r["action"] for r in refus}
    assert plat.db.query("SELECT * FROM alerts WHERE type='action_interdite' AND agent_id=?", (org["a1"]["id"],))


# 5 --------------------------------------------------------------------------------------------
def test_05_request_circulates_accepted_refused_escalated_copied(plat, org):
    import datetime as dt
    before = len(plat.bus.recent)
    r1 = plat.messaging.request(A(org, "s1"), "aide", "Aide sur un devis", "Client exigeant", "Signature rapide")
    events = list(plat.bus.recent)[before:]
    assert any(e["type"] == "message" and e["kind"] == "demande" and e["de"] == org["s1"]["id"] for e in events)  # animation
    assert plat.messaging.decide(A(org, "r1"), r1["id"], True)["statut"] == "acceptee"
    r2 = plat.messaging.request(A(org, "s2"), "budget", "Plus de budget", "Beaucoup d'appels", payload={"budget_jour_eur": 2})
    assert plat.messaging.decide(A(org, "r1"), r2["id"], False, "Pas ce mois-ci")["statut"] == "refusee"
    r3 = plat.messaging.request(A(org, "s1"), "validation", "Valider la campagne", "Lancement lundi")
    out = plat.messaging.escalate_overdue(at=now() + dt.timedelta(hours=plat.cfg.messaging.escalation_hours + 1))
    assert out[0]["id"] == r3["id"] and out[0]["a"] == org["chef"]["id"]
    assert plat.db.query("SELECT * FROM alerts WHERE type='demande_escaladee'")
    for r in (r1, r2, r3):
        note = (plat.vault_dir / plat.messaging.get_request(r["id"])["vault_path"]).read_text(encoding="utf-8")
        assert r["sujet"] in note


# 6 --------------------------------------------------------------------------------------------
def test_06_peers_talk_directly_and_infinite_loop_is_blocked(plat, org):
    m = plat.messaging.send(A(org, "s1"), org["s2"]["id"], "Collab", "On se partage la liste ?")
    assert m["a"] == org["s2"]["id"]
    plat.cfg.messaging.max_messages_per_agent_per_hour = 10
    with pytest.raises(RateLimited):
        for i in range(100):
            who, to = ("s1", "s2") if i % 2 else ("s2", "s1")
            plat.messaging.send(A(org, who), org[to]["id"], "ping", str(i), thread_id=m["thread_id"])
    assert plat.db.query("SELECT * FROM alerts WHERE type='boucle_messages'")


# 7 --------------------------------------------------------------------------------------------
def test_07_skill_created_tested_reviewed_published_reused_with_stats(plat, org, api):
    s = plat.skills.create(A(org, "r1"), {
        "nom": "score-prospect", "portee": "equipe",
        "contenu": "## Quand l'utiliser\nNoter un prospect de 0 à 10.\n## Étapes\nDonner le nombre de salariés en entrée.",
        "code": "import sys\nn=int(sys.stdin.read() or 0)\nprint(min(10, n // 10))",
        "tests": [{"entree": "55", "attendu": "5"}, {"entree": "300", "attendu": "10"}]})
    assert s["statut"] == "approuve" and s["portee"] == "equipe"
    steps = [r["action"] for r in plat.db.query("SELECT action FROM log_index WHERE cible='score-prospect' ORDER BY seq")]
    assert steps[:4] == ["creation", "auto_test_ok", "revue_approuvee", "publication"]
    replies = iter(['{"actions": [{"outil": "utiliser_skill", "args": {"nom": "score-prospect", "entree": "80"}}]}', '{"final": "score 8"}'])
    use_mock(plat, org["s2"]["id"], lambda m, msgs: next(replies))
    t = plat.runtime.assign(OWNER, org["s2"]["id"], "Note le prospect de 80 salariés", background=False)
    plat.runtime.validate(OWNER, t["id"], True)
    row = [x for x in api.get("/api/skills", headers=H).json() if x["nom"] == "score-prospect"][0]
    assert row["utilisations"] == 1 and row["taux_reussite"] == 1.0 and row["evaluations"] == 1


# 8 --------------------------------------------------------------------------------------------
def test_08_manual_log_tampering_is_detected(plat, org, api):
    assert api.get("/api/logs/verify", headers=H).json()["ok"]
    f = sorted(plat.logs_dir.glob("*.jsonl"))[-1]
    lines = f.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[5])
    e["action"] = "rien_a_voir"
    lines[5] = json.dumps(e, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    r = api.get("/api/logs/verify", headers=H).json()
    assert not r["ok"] and r["erreurs"]
    assert plat.db.query("SELECT * FROM alerts WHERE type='integrite_logs' AND gravite='critique'")
    r = subprocess.run(["python3", "-m", "orchestra", "verify-logs"], cwd=plat.root, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(REPO / "platform"), "ORCHESTRA_ROOT": str(plat.root)})
    assert r.returncode == 2 and "COMPROMISE" in r.stdout


# 9 --------------------------------------------------------------------------------------------
def test_09_budget_blocks_beyond_100_eur_and_alerts_at_80(plat, org):
    assert plat.cfg.budget.monthly_eur == 100
    plat.budget.record_expense(OWNER, 79.0, "outils")
    assert not plat.db.query("SELECT * FROM alerts WHERE type='budget_80'")
    plat.budget.record_expense(OWNER, 2.0, "outils")  # 81 %
    assert plat.db.query("SELECT * FROM alerts WHERE type='budget_80'")
    s1 = plat.agents.update(OWNER, org["s1"]["id"], {"budget_jour_eur": 100})
    use_mock(plat, s1["id"], lambda m, msgs: "x" * 4000, price_out=5000)  # 1000 tokens = 5 €
    for _ in range(3):
        plat.gateway.chat(plat.agents.get(s1["id"]), [{"role": "user", "content": "x"}], max_tokens=1000)
    with pytest.raises(BudgetExceeded):
        for _ in range(10):
            plat.gateway.chat(plat.agents.get(s1["id"]), [{"role": "user", "content": "x"}], max_tokens=1000)
    with pytest.raises(BudgetExceeded):
        plat.budget.record_expense(OWNER, 5.0, "dépassement")
    assert plat.budget.month_spent() <= 100.0
    assert plat.db.query("SELECT * FROM alerts WHERE type='budget_100'")


# 10 -------------------------------------------------------------------------------------------
def test_10_emergency_stop_freezes_all_agents_under_5s(plat, org, api):
    def slow(m, msgs):
        time.sleep(30)
        return '{"final": "x"}'
    use_mock(plat, org["s1"]["id"], slow)
    ids = []
    for k in ("s1", "s2", "s3"):
        plat.db.execute("UPDATE agents SET modele='mock/m' WHERE id=?", (org[k]["id"],))
        ids.append(plat.runtime.assign(OWNER, org[k]["id"], "tâche longue")["id"])
    time.sleep(0.5)
    t0 = time.monotonic()
    assert api.post("/api/emergency/stop", json={"raison": "recette"}, headers=H).json()["active"]
    for t in ids:
        plat.runtime.wait(t, 5)
    elapsed = time.monotonic() - t0
    assert elapsed < 5, elapsed
    assert all(plat.runtime.task(t)["statut"] in ("gelee", "en_attente") for t in ids)
    assert api.post(f"/api/agents/{org['s1']['id']}/tasks", json={"consigne": "x"}, headers=H).status_code == 423
    api.post("/api/emergency/resume", headers=H)
    assert plat.emergency.self_test()["ok"]  # test périodique du mécanisme


# 11 -------------------------------------------------------------------------------------------
def test_11_simulated_degradation_triggers_automatic_rollback(plat, org):
    sid = org["s3"]["id"]

    def tasks(version, results):
        for ok in results:
            tid = new_id("tache")
            plat.db.execute("INSERT INTO tasks(id,agent_id,agent_version,consigne,statut,debut,fin) VALUES(?,?,?,?,?,?,?)",
                            (tid, sid, version, "x", "terminee", now_iso(), now_iso()))
            plat.runtime.validate(OWNER, tid, ok, None if ok else "qualité")

    plat.agents.update(OWNER, sid, {"instructions": "Méthode éprouvée"})  # v2
    tasks(2, [True] * 5)
    plat.agents.update(A(org, "s3"), sid, {"instructions": "Méthode expérimentale"}, "auto-amélioration")  # v3
    tasks(3, [False, False, True, False, False])
    a = plat.agents.get(sid)
    assert a["instructions"] == "Méthode éprouvée" and a["version"] == 4
    assert plat.db.query("SELECT * FROM log_index WHERE action='retour_arriere'")


# 12 -------------------------------------------------------------------------------------------
def test_12_no_secret_in_logs_or_vault(plat, org, api):
    secret = "gsk_testsecretvalue1234567890"  # valeur réelle de .env dans ce test
    plat.messaging.send(A(org, "s1"), org["s2"]["id"], "clé", f"voici {secret} et sk-proj-{'a' * 30}")
    plat.agents.update(OWNER, org["s1"]["id"], {"contexte": f"api_key={secret}"})
    plat.audit.record("test", "fuite", details={"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz"})
    with pytest.raises(Exception):
        plat.skills.create(A(org, "s1"), {"nom": "fuite", "contenu": f"clé {secret}"})
    plat.scribe.write_agent_note(A(org, "s1"), "notes.md", f"ma clé {secret}")
    plat.git.flush()
    assert scan_paths([plat.logs_dir, plat.vault_dir], plat.env) == []
    r = subprocess.run(["python3", "-m", "orchestra", "scan-secrets"], cwd=plat.root, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(REPO / "platform"), "ORCHESTRA_ROOT": str(plat.root)})
    assert r.returncode == 0, r.stdout
    # et la recherche détecte bien un secret s'il y en avait un
    (plat.vault_dir / "fuite-manuelle.md").write_text(secret, encoding="utf-8")
    assert scan_paths([plat.vault_dir], plat.env)
