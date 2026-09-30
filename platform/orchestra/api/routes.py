"""Routes REST du tableau de bord. Toutes les actions sont faites au nom du Propriétaire."""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from fastapi import Depends, FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orchestra.models import OWNER, OrchestraError


class AgentIn(BaseModel):
    nom: str
    niveau: str = "salarie"
    parent_id: str | None = None
    statut: str = "actif"
    modele: str | None = None
    role: str = ""
    contexte: str = ""
    instructions: str = ""
    objectif: str = ""
    kpi: list[str] = []
    outils: list[str] = []
    skills: list[str] = []
    interdits: str = ""
    budget_jour_eur: float | None = None
    budget_mois_eur: float | None = None


class AgentPatch(BaseModel):
    nom: str | None = None
    parent_id: str | None = None
    modele: str | None = None
    role: str | None = None
    contexte: str | None = None
    instructions: str | None = None
    objectif: str | None = None
    kpi: list[str] | None = None
    outils: list[str] | None = None
    skills: list[str] | None = None
    interdits: str | None = None
    journal: str | None = None
    budget_jour_eur: float | None = None
    budget_mois_eur: float | None = None
    raison: str | None = None


class Reason(BaseModel):
    raison: str = ""
    new_parent_id: str | None = None


class TaskIn(BaseModel):
    consigne: str


class ValidateIn(BaseModel):
    succes: bool
    point_echec: str | None = None
    commentaire: str = ""


class MoneyIn(BaseModel):
    montant_eur: float
    description: str
    agent_id: str | None = None


class MessageIn(BaseModel):
    a: str
    sujet: str
    corps: str
    thread_id: str | None = None
    priorite: str = "normale"


class RelayIn(BaseModel):
    a: str
    commentaire: str = ""


class DecideIn(BaseModel):
    accepter: bool
    reponse: str = ""


def register(app: FastAPI, p, auth) -> None:
    dep = [Depends(auth)]

    # ------------------------------------------------------------------ agents
    @app.get("/api/agents", dependencies=dep)
    def list_agents(include_archived: bool = True) -> list[dict]:
        return p.agents.list(include_archived)

    @app.post("/api/agents", dependencies=dep)
    def create_agent(body: AgentIn) -> dict:
        data = body.model_dump()
        if data["budget_jour_eur"] is None:
            data.pop("budget_jour_eur")
        return p.agents.create(OWNER, data)

    @app.get("/api/agents/{agent_id}", dependencies=dep)
    def get_agent(agent_id: str) -> dict:
        return p.agents.get(agent_id)

    @app.patch("/api/agents/{agent_id}", dependencies=dep)
    def patch_agent(agent_id: str, body: AgentPatch) -> dict:
        changes = body.model_dump(exclude_unset=True)
        raison = changes.pop("raison", None) or "modification par le Propriétaire"
        return p.agents.update(OWNER, agent_id, changes, raison)

    @app.post("/api/agents/{agent_id}/{action}", dependencies=dep)
    def agent_action(agent_id: str, action: str, body: Reason | None = None) -> dict:
        body = body or Reason()
        if action in ("pause", "resume", "activate", "archive"):
            statut = {"pause": "pause", "resume": "actif", "activate": "actif", "archive": "archive"}[action]
            return p.agents.set_status(OWNER, agent_id, statut, body.raison)
        if action == "promote":
            return p.agents.promote(OWNER, agent_id, body.new_parent_id, body.raison or "promotion par le Propriétaire")
        if action == "demote":
            return p.agents.demote(OWNER, agent_id, body.new_parent_id, body.raison or "rétrogradation par le Propriétaire")
        raise OrchestraError(f"action inconnue : {action}")

    @app.get("/api/agents/{agent_id}/versions", dependencies=dep)
    def versions(agent_id: str) -> list[dict]:
        return p.agents.versions(agent_id)

    @app.post("/api/agents/{agent_id}/restore/{version}", dependencies=dep)
    def restore(agent_id: str, version: int) -> dict:
        return p.agents.restore_version(OWNER, agent_id, version)

    # ------------------------------------------------------------------ logs
    def _logs_query(q: str | None, agent_id: str | None, niveau: str | None, type_evenement: str | None,
                    gravite: str | None, since: str | None, until: str | None, limit: int, offset: int) -> list[dict]:
        where, params = [], []
        if q:
            terms = " ".join(f'"{t}"' for t in re.findall(r"[\w\-]+", q, flags=re.UNICODE))
            if terms:
                where.append("seq IN (SELECT rowid FROM log_fts WHERE log_fts MATCH ?)")
                params.append(terms)
        for col, val in (("agent_id", agent_id), ("niveau", niveau), ("type_evenement", type_evenement), ("gravite", gravite)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        if since:
            where.append("horodatage>=?")
            params.append(since)
        if until:
            where.append("horodatage<=?")
            params.append(until + "￿" if len(until) == 10 else until)
        sql = "SELECT * FROM log_index" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY seq DESC LIMIT ? OFFSET ?"
        rows = p.db.query(sql, (*params, limit, offset))
        for r in rows:
            r.pop("ligne", None)
        return rows

    @app.get("/api/logs", dependencies=dep)
    def logs(q: str | None = None, agent_id: str | None = None, niveau: str | None = None,
             type_evenement: str | None = None, gravite: str | None = None, since: str | None = None,
             until: str | None = None, limit: int = Query(200, le=5000), offset: int = 0) -> list[dict]:
        return _logs_query(q, agent_id, niveau, type_evenement, gravite, since, until, limit, offset)

    @app.get("/api/logs/export.csv", dependencies=dep)
    def logs_csv(q: str | None = None, agent_id: str | None = None, niveau: str | None = None,
                 type_evenement: str | None = None, gravite: str | None = None, since: str | None = None,
                 until: str | None = None):
        rows = _logs_query(q, agent_id, niveau, type_evenement, gravite, since, until, 100000, 0)
        buf = io.StringIO()
        cols = ["seq", "horodatage", "agent_id", "niveau", "type_evenement", "action", "cible", "resultat",
                "gravite", "cout_tokens", "cout_eur", "correlation_id"]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", delimiter=";")
        w.writeheader()
        w.writerows(rows)
        p.audit.record("tableau_de_bord", "export_logs_csv", agent_id=OWNER.id, niveau="proprietaire", details={"lignes": len(rows)})
        return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=orchestra-logs.csv"})

    @app.get("/api/logs/verify", dependencies=dep)
    def verify() -> dict[str, Any]:
        rep = p.verify_logs()
        if not rep.ok:
            p.alerts.raise_("integrite_logs", "Intégrité des logs compromise : " + "; ".join(rep.errors[:3]), gravite="critique")
        return {"ok": rep.ok, "fichiers": rep.files, "lignes": rep.lines, "erreurs": rep.errors}

    # ------------------------------------------------------------------ alertes
    @app.get("/api/alerts", dependencies=dep)
    def alerts(only_unread: bool = False) -> list[dict]:
        return p.alerts.list(only_unread)

    @app.post("/api/alerts/{alert_id}/read", dependencies=dep)
    def alert_read(alert_id: int) -> dict:
        p.alerts.mark_read(alert_id)
        return {"ok": True}

    @app.get("/api/events/recent", dependencies=dep)
    def recent_events() -> list[dict]:
        return list(p.bus.recent)[-200:]

    # ------------------------------------------------------------------ tâches
    @app.post("/api/agents/{agent_id}/tasks", dependencies=dep)
    def assign_task(agent_id: str, body: TaskIn) -> dict:
        return p.runtime.assign(OWNER, agent_id, body.consigne)

    @app.get("/api/tasks", dependencies=dep)
    def tasks(agent_id: str | None = None, limit: int = 100) -> list[dict]:
        if agent_id:
            return p.db.query("SELECT * FROM tasks WHERE agent_id=? ORDER BY debut DESC LIMIT ?", (agent_id, limit))
        return p.db.query("SELECT * FROM tasks ORDER BY debut DESC LIMIT ?", (limit,))

    @app.get("/api/tasks/{task_id}", dependencies=dep)
    def task(task_id: str) -> dict:
        return p.runtime.task(task_id)

    @app.post("/api/tasks/{task_id}/validate", dependencies=dep)
    def validate_task(task_id: str, body: ValidateIn) -> dict:
        return p.runtime.validate(OWNER, task_id, body.succes, body.point_echec, body.commentaire)

    # ------------------------------------------------------------------ budget
    @app.get("/api/budget", dependencies=dep)
    def budget() -> dict:
        return p.budget.summary()

    @app.get("/api/agents/{agent_id}/costs", dependencies=dep)
    def agent_costs(agent_id: str) -> dict:
        return p.budget.agent_costs(agent_id)

    @app.post("/api/budget/expense", dependencies=dep)
    def expense(body: MoneyIn) -> dict:
        p.budget.record_expense(OWNER, body.montant_eur, body.description, body.agent_id)
        return p.budget.summary()

    @app.post("/api/budget/revenue", dependencies=dep)
    def revenue(body: MoneyIn) -> dict:
        p.budget.record_revenue(OWNER, body.montant_eur, body.description)
        return p.budget.summary()

    # ------------------------------------------------------------------ arrêt d'urgence
    @app.post("/api/emergency/stop", dependencies=dep)
    def emergency_stop(body: Reason | None = None) -> dict:
        return p.emergency.stop(OWNER, (body.raison if body else "") or "arrêt d'urgence depuis le tableau de bord")

    @app.post("/api/emergency/resume", dependencies=dep)
    def emergency_resume() -> dict:
        return p.emergency.resume(OWNER)

    # ------------------------------------------------------------------ messages et demandes
    @app.get("/api/messages", dependencies=dep)
    def messages(agent_id: str | None = None, thread_id: str | None = None, limit: int = 200) -> list[dict]:
        if thread_id:
            return p.messaging.thread(thread_id)
        if agent_id:
            return p.messaging.for_agent(agent_id, limit)
        return p.db.query("SELECT * FROM messages ORDER BY horodatage DESC LIMIT ?", (limit,))

    @app.post("/api/messages", dependencies=dep)
    def send_message(body: MessageIn) -> dict:
        return p.messaging.send(OWNER, body.a, body.sujet, body.corps, thread_id=body.thread_id, priorite=body.priorite)

    @app.post("/api/messages/{message_id}/relay", dependencies=dep)
    def relay(message_id: str, body: RelayIn) -> dict:
        return p.messaging.relay(OWNER, message_id, body.a, body.commentaire)

    @app.get("/api/requests", dependencies=dep)
    def requests_(pending: bool = False, agent_id: str | None = None) -> list[dict]:
        if pending:
            return p.messaging.pending()
        if agent_id:
            return p.messaging.requests_for(agent_id)
        return p.db.query("SELECT * FROM requests ORDER BY cree_le DESC LIMIT 500")

    @app.post("/api/requests/{request_id}/decide", dependencies=dep)
    def decide(request_id: str, body: DecideIn) -> dict:
        return p.messaging.decide(OWNER, request_id, body.accepter, body.reponse)

    @app.post("/api/requests/escalate", dependencies=dep)
    def escalate_now() -> list[dict]:
        return p.messaging.escalate_overdue()

    # ------------------------------------------------------------------ coffre / second cerveau
    @app.get("/api/search", dependencies=dep)
    def search(q: str, limit: int = 20, any_term: bool = False) -> list[dict]:
        return p.scribe.search(q, OWNER, limit, any_term=any_term)

    @app.get("/api/vault/note", dependencies=dep)
    def read_note(path: str) -> dict:
        return {"path": path, "contenu": p.scribe.read_as(OWNER, path)}

    @app.post("/api/vault/reindex", dependencies=dep)
    def reindex() -> dict:
        return {"notes": p.scribe.reindex()}

    @app.get("/api/agents/{agent_id}/history", dependencies=dep)
    def agent_history(agent_id: str) -> dict:
        a = p.agents.get(agent_id)
        return {"commits": p.git.log(a["vault_path"], 50), "versions": p.agents.versions(agent_id)}

    for extra in getattr(p, "route_registrars", []):
        extra(app, p, dep)
