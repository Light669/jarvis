"""Base SQLite (mode WAL + FTS5) : agents, messages, demandes, skills, tâches, budget, alertes."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  nom TEXT NOT NULL,
  niveau TEXT NOT NULL CHECK (niveau IN ('chef','responsable','salarie','apprenti')),
  parent_id TEXT REFERENCES agents(id),
  statut TEXT NOT NULL CHECK (statut IN ('brouillon','actif','pause','archive')),
  modele TEXT NOT NULL,
  budget_jour_eur REAL NOT NULL DEFAULT 0.5,
  budget_mois_eur REAL,
  outils TEXT NOT NULL DEFAULT '[]',
  skills TEXT NOT NULL DEFAULT '[]',
  kpi TEXT NOT NULL DEFAULT '[]',
  role TEXT NOT NULL DEFAULT '',
  contexte TEXT NOT NULL DEFAULT '',
  instructions TEXT NOT NULL DEFAULT '',
  objectif TEXT NOT NULL DEFAULT '',
  interdits TEXT NOT NULL DEFAULT '',
  journal TEXT NOT NULL DEFAULT '',
  cree_par TEXT NOT NULL,
  cree_le TEXT NOT NULL,
  modifie_le TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  vault_path TEXT,
  archive_raison TEXT,
  activite TEXT NOT NULL DEFAULT 'inactif',
  activite_detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS agent_versions (
  agent_id TEXT NOT NULL, version INTEGER NOT NULL, snapshot TEXT NOT NULL,
  auteur TEXT NOT NULL, horodatage TEXT NOT NULL, raison TEXT,
  PRIMARY KEY (agent_id, version)
);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'message',
  de TEXT NOT NULL, a TEXT NOT NULL, sujet TEXT NOT NULL, corps TEXT NOT NULL,
  thread_id TEXT NOT NULL, parent_id TEXT, profondeur INTEGER NOT NULL DEFAULT 1,
  priorite TEXT NOT NULL DEFAULT 'normale', horodatage TEXT NOT NULL,
  statut TEXT NOT NULL DEFAULT 'envoye', relaye_de TEXT, vault_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_a ON messages(a, statut);
CREATE INDEX IF NOT EXISTS idx_messages_de ON messages(de, horodatage);
CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY, message_id TEXT, type TEXT NOT NULL,
  de TEXT NOT NULL, a TEXT NOT NULL, sujet TEXT NOT NULL,
  justification TEXT NOT NULL, gain_attendu TEXT NOT NULL DEFAULT '',
  cout_eur REAL NOT NULL DEFAULT 0, statut TEXT NOT NULL DEFAULT 'en_attente',
  reponse TEXT, decide_par TEXT, cree_le TEXT NOT NULL, maj_le TEXT NOT NULL,
  escalades INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL DEFAULT '{}', vault_path TEXT
);
CREATE TABLE IF NOT EXISTS skills (
  id TEXT PRIMARY KEY, nom TEXT NOT NULL UNIQUE, portee TEXT NOT NULL,
  equipe_id TEXT, auteur TEXT NOT NULL, statut TEXT NOT NULL DEFAULT 'brouillon',
  version INTEGER NOT NULL DEFAULT 1, permissions_requises TEXT NOT NULL DEFAULT '[]',
  tests TEXT NOT NULL DEFAULT '[]', code TEXT NOT NULL DEFAULT '', contenu TEXT NOT NULL DEFAULT '',
  utilisations INTEGER NOT NULL DEFAULT 0, succes INTEGER NOT NULL DEFAULT 0,
  echecs INTEGER NOT NULL DEFAULT 0, cout_total_eur REAL NOT NULL DEFAULT 0,
  derniere_utilisation TEXT, cree_le TEXT NOT NULL, maj_le TEXT NOT NULL,
  vault_path TEXT, fusionne_dans TEXT, revue TEXT
);
CREATE TABLE IF NOT EXISTS skill_versions (
  skill_id TEXT NOT NULL, version INTEGER NOT NULL, snapshot TEXT NOT NULL,
  auteur TEXT NOT NULL, horodatage TEXT NOT NULL, raison TEXT,
  PRIMARY KEY (skill_id, version)
);
CREATE TABLE IF NOT EXISTS skill_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, skill_id TEXT NOT NULL, skill_version INTEGER NOT NULL,
  agent_id TEXT NOT NULL, task_id TEXT, succes INTEGER, cout_eur REAL NOT NULL DEFAULT 0,
  horodatage TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, agent_version INTEGER NOT NULL,
  consigne TEXT NOT NULL, statut TEXT NOT NULL DEFAULT 'en_cours', resultat TEXT,
  succes INTEGER, point_echec TEXT, valide_par TEXT, cout_eur REAL NOT NULL DEFAULT 0,
  tokens INTEGER NOT NULL DEFAULT 0, debut TEXT NOT NULL, fin TEXT, correlation_id TEXT,
  skills_utilises TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_id, fin);
CREATE TABLE IF NOT EXISTS budget_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT, horodatage TEXT NOT NULL, agent_id TEXT,
  kind TEXT NOT NULL, montant_eur REAL NOT NULL, tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0, modele TEXT, description TEXT
);
CREATE INDEX IF NOT EXISTS idx_budget_time ON budget_entries(horodatage);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, horodatage TEXT NOT NULL, gravite TEXT NOT NULL,
  type TEXT NOT NULL, message TEXT NOT NULL, agent_id TEXT, lue INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS learnings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL, task_id TEXT,
  succes INTEGER, texte TEXT NOT NULL, horodatage TEXT NOT NULL, vault_path TEXT
);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vault_state (path TEXT PRIMARY KEY, hash TEXT NOT NULL, maj TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS log_index (
  seq INTEGER PRIMARY KEY, horodatage TEXT NOT NULL, agent_id TEXT, niveau TEXT,
  type_evenement TEXT NOT NULL, action TEXT NOT NULL, cible TEXT, resultat TEXT,
  gravite TEXT, cout_tokens INTEGER, cout_eur REAL, correlation_id TEXT, ligne TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_agent ON log_index(agent_id, horodatage);
CREATE VIRTUAL TABLE IF NOT EXISTS log_fts USING fts5(texte, tokenize='unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE IF NOT EXISTS vault_fts USING fts5(
  path UNINDEXED, type UNINDEXED, titre, contenu, tokenize='unicode61 remove_diacritics 2'
);
"""

JSON_FIELDS = {"outils", "skills", "kpi", "permissions_requises", "tests", "payload", "skills_utilises", "snapshot"}


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(SCHEMA)

    # --- helpers -----------------------------------------------------------
    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, params)

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self.lock:
            return [decode(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        with self.lock:
            r = self.conn.execute(sql, params).fetchone()
            return decode(r) if r else None

    def scalar(self, sql: str, params: tuple | dict = ()) -> Any:
        with self.lock:
            r = self.conn.execute(sql, params).fetchone()
            return r[0] if r else None

    def transaction(self):
        return _Tx(self)

    def get_state(self, key: str, default: str | None = None) -> str | None:
        v = self.scalar("SELECT value FROM state WHERE key=?", (key,))
        return default if v is None else v

    def set_state(self, key: str, value: str) -> None:
        self.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def close(self) -> None:
        with self.lock:
            self.conn.close()


class _Tx:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self):
        self.db.lock.acquire()
        self.db.conn.execute("BEGIN IMMEDIATE")
        return self.db

    def __exit__(self, exc_type, exc, tb):
        try:
            self.db.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            self.db.lock.release()
        return False


def decode(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for k in JSON_FIELDS & d.keys():
        if isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    return d


def enc(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
