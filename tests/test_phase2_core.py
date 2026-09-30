"""Phase 2 : base, permissions, journal chaîné, masquage, API."""
import json

import pytest
from fastapi.testclient import TestClient

from orchestra.audit import verify_chain
from orchestra.models import OWNER, OrchestraError, PermissionDenied, agent_actor
from orchestra.redact import Redactor


def actor(org, key):
    return agent_actor(org[key])


# ---------------------------------------------------------------- permissions
def test_owner_can_everything(plat, org):
    for action in ["agent.create", "agent.lifecycle", "platform.modify", "emergency.resume", "budget.set"]:
        assert plat.perms.check(OWNER, action, org["chef"])


def test_nobody_modifies_logs(plat, org):
    assert not plat.perms.check(OWNER, "logs.modify")
    assert not plat.perms.check(actor(org, "chef"), "logs.delete")


@pytest.mark.parametrize("who,niveau,parent,ok", [
    ("chef", "responsable", "chef", True),
    ("chef", "salarie", "r1", True),
    ("chef", "chef", None, False),
    ("r1", "apprenti", "s1", True),     # dans son équipe
    ("r1", "apprenti", "s3", False),    # autre équipe
    ("r1", "salarie", "r1", False),     # ne crée pas de salarié
    ("r1", "responsable", "chef", False),
    ("s1", "apprenti", "s1", False),    # salarié : pas de création
    ("a1", "apprenti", "s1", False),
])
def test_create_matrix(plat, org, who, niveau, parent, ok):
    d = plat.perms.check(actor(org, who), "agent.create", None, niveau=niveau, parent_id=org[parent]["id"] if parent else None)
    assert bool(d) is ok, d.reason


def test_self_edit_limited_to_safe_fields(plat, org):
    s1 = actor(org, "s1")
    assert plat.perms.check(s1, "agent.update", org["s1"], fields={"instructions", "journal"})
    assert not plat.perms.check(s1, "agent.update", org["s1"], fields={"budget_jour_eur"})
    assert not plat.perms.check(s1, "agent.update", org["s1"], fields={"outils"})
    r1 = actor(org, "r1")
    assert not plat.perms.check(r1, "agent.update", org["r1"], fields={"budget_mois_eur"})  # son propre budget
    assert plat.perms.check(r1, "agent.update", org["a1"], fields={"instructions"})
    assert not plat.perms.check(r1, "agent.update", org["a2"], fields={"instructions"})  # autre équipe
    assert not plat.perms.check(r1, "agent.update", org["s1"], fields={"niveau"})


def test_lifecycle_only_chef_or_owner(plat, org):
    assert plat.perms.check(actor(org, "chef"), "agent.lifecycle", org["s1"])
    assert not plat.perms.check(actor(org, "chef"), "agent.lifecycle", org["chef"])
    assert not plat.perms.check(actor(org, "r1"), "agent.lifecycle", org["s1"])


def test_spending_and_platform(plat, org):
    assert plat.perms.check(actor(org, "r1"), "spend.external")
    assert not plat.perms.check(actor(org, "s1"), "spend.external")
    assert not plat.perms.check(actor(org, "chef"), "platform.modify")


def test_tools_from_fiche(plat, org):
    assert plat.perms.check(actor(org, "s1"), "tool.use", "recherche_web")
    assert not plat.perms.check(actor(org, "s2"), "tool.use", "recherche_web")
    assert not plat.perms.check(actor(org, "a1"), "tool.use", "executer_code")


def test_vault_write_perimeter(plat, org):
    a1 = actor(org, "a1")
    ws = org["a1"]["vault_path"][:-3] + "/"
    assert plat.perms.check(a1, "vault.write", ws + "notes.md")
    assert not plat.perms.check(a1, "vault.write", "Agents/Chef/chef.md")
    assert not plat.perms.check(a1, "vault.write", ws + "../../Chef/x.md")


def test_denial_is_logged_and_alerted(plat, org):
    with pytest.raises(PermissionDenied):
        plat.perms.require(actor(org, "a1"), "agent.create", None, niveau="apprenti", parent_id=org["s1"]["id"])
    rows = plat.db.query("SELECT * FROM log_index WHERE type_evenement='permission_refusee'")
    assert rows and rows[-1]["agent_id"] == org["a1"]["id"]
    assert plat.db.query("SELECT * FROM alerts WHERE type='action_interdite'")


# ---------------------------------------------------------------- agents
def test_hierarchy_validation(plat, org):
    with pytest.raises(OrchestraError):
        plat.agents.create(OWNER, {"nom": "X", "niveau": "salarie", "parent_id": org["chef"]["id"]})
    with pytest.raises(OrchestraError):
        plat.agents.create(OWNER, {"nom": "Chef2", "niveau": "chef"})


def test_update_versions_and_logs(plat, org):
    a = plat.agents.update(OWNER, org["s1"]["id"], {"instructions": "Nouvelles consignes"})
    assert a["version"] == 2
    vs = plat.agents.versions(a["id"])
    assert [v["version"] for v in vs] == [2, 1]
    log = plat.db.query("SELECT * FROM log_index WHERE action='modification_fiche' AND cible=?", (a["id"],))[-1]
    details = json.loads(log["ligne"])["details"]
    assert details["avant"]["instructions"] == "" and details["apres"]["instructions"] == "Nouvelles consignes"
    r = plat.agents.restore_version(OWNER, a["id"], 1)
    assert r["instructions"] == "" and r["version"] == 3


def test_lifecycle_never_deletes(plat, org):
    a = plat.agents.set_status(OWNER, org["a2"]["id"], "pause")
    assert a["statut"] == "pause"
    a = plat.agents.set_status(OWNER, org["a2"]["id"], "archive", "test")
    assert a["statut"] == "archive" and a["archive_raison"] == "test"
    with pytest.raises(OrchestraError):
        plat.agents.set_status(OWNER, org["a2"]["id"], "actif")
    with pytest.raises(OrchestraError):  # subordonnés actifs
        plat.agents.set_status(OWNER, org["s1"]["id"], "archive", "x")


def test_promotion_path(plat, org):
    a = plat.agents.promote(OWNER, org["a1"]["id"])
    assert a["niveau"] == "salarie" and a["parent_id"] == org["r1"]["id"]
    assert a["vault_path"].startswith("Agents/Salaries/")
    d = plat.agents.demote(OWNER, a["id"], org["s2"]["id"])
    assert d["niveau"] == "apprenti" and d["parent_id"] == org["s2"]["id"]


# ---------------------------------------------------------------- journal
def test_hash_chain_detects_tampering(plat, org):
    assert plat.verify_logs().ok
    f = sorted(plat.logs_dir.glob("*.jsonl"))[-1]
    lines = f.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[2])
    entry["resultat"] = "falsifié"
    lines[2] = json.dumps(entry, ensure_ascii=False)
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rep = plat.verify_logs()
    assert not rep.ok and any("altéré" in e for e in rep.errors)


def test_hash_chain_detects_deletion_and_truncation(plat, org):
    f = sorted(plat.logs_dir.glob("*.jsonl"))[-1]
    lines = f.read_text(encoding="utf-8").splitlines()
    f.write_text("\n".join(lines[:3] + lines[4:]) + "\n", encoding="utf-8")
    assert not verify_chain(plat.logs_dir).ok
    f.write_text("\n".join(lines[:-2]) + "\n", encoding="utf-8")
    assert verify_chain(plat.logs_dir).ok  # troncature seule : invisible sans la tête mémorisée...
    assert not plat.verify_logs().ok       # ...mais détectée grâce à la tête en base


def test_chain_continues_after_restart(root):
    from orchestra.platform import Platform
    p = Platform(root); p.audit.record("test", "a"); p.close()
    p = Platform(root); p.audit.record("test", "b")
    assert p.verify_logs().ok
    p.close()


# ---------------------------------------------------------------- masquage
def test_redaction():
    r = Redactor({"GROQ_API_KEY": "gsk_realkey_ABCDEFGHIJ12345"})
    txt = "clé gsk_realkey_ABCDEFGHIJ12345 et sk-proj-abcdefghijklmnopqrstuvwxyz mail jean.dupont@exemple.fr tel 06 12 34 56 78"
    out = r.full(txt)
    assert "gsk_" not in out and "sk-proj" not in out and "@" not in out and "06 12" not in out
    assert r.obj({"api_key": "abc", "x": ["AIzaSyA1234567890abcdefghijklmnopqrstu"]}) == {"api_key": "***", "x": ["***"]}


def test_secrets_never_in_logs(plat):
    plat.audit.record("test", "appel", details={"cle": "gsk_testsecretvalue1234567890", "Authorization": "Bearer abcdefghijklmnopqrstuv"})
    content = "".join(f.read_text(encoding="utf-8") for f in plat.logs_dir.glob("*.jsonl"))
    assert "gsk_testsecretvalue" not in content and "abcdefghijklmnopqrstuv" not in content


# ---------------------------------------------------------------- API
@pytest.fixture()
def client(plat):
    from orchestra.api.app import create_app
    app = create_app(platform=plat, background=False)
    with TestClient(app) as c:
        yield c


H = {"Authorization": "Bearer test-token-0123456789"}


def test_api_requires_token(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/agents").status_code == 401
    assert client.get("/api/agents", headers={"Authorization": "Bearer faux"}).status_code == 401


def test_api_agent_crud_and_logs(client):
    r = client.post("/api/agents", json={"nom": "Chef", "niveau": "chef"}, headers=H)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    r = client.post("/api/agents", json={"nom": "Resp", "niveau": "responsable", "parent_id": cid}, headers=H)
    rid = r.json()["id"]
    r = client.patch(f"/api/agents/{rid}", json={"contexte": "Équipe ventes"}, headers=H)
    assert r.json()["version"] == 2
    assert client.post(f"/api/agents/{rid}/pause", json={}, headers=H).json()["statut"] == "pause"
    assert client.post(f"/api/agents/{rid}/archive", json={}, headers=H).status_code == 400  # raison obligatoire
    logs = client.get("/api/logs", params={"q": "modification_fiche"}, headers=H).json()
    assert logs and logs[0]["cible"] == rid
    assert client.get("/api/logs", params={"agent_id": "proprietaire", "type_evenement": "tableau_de_bord"}, headers=H).json()
    csv_text = client.get("/api/logs/export.csv", headers=H).text
    assert "type_evenement" in csv_text.splitlines()[0]
    assert client.get("/api/logs/verify", headers=H).json()["ok"]


def test_ws_requires_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=faux") as ws:
            ws.receive_json()
