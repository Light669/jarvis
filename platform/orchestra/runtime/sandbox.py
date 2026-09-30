"""Exécution isolée du code des agents et des skills.

- DockerSandbox : conteneur jetable, sans réseau, système de fichiers en lecture seule, non-root,
  sans capacités, limites CPU / RAM / PID / temps, un seul volume (/work).
- SubprocessSandbox : repli si Docker est indisponible (isolation dégradée, signalée).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

LABEL = "orchestra.sandbox=1"


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    isolation: str  # "docker" | "degradee"
    killed: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.killed


def _clip(s: str, n: int = 20000) -> str:
    return s if len(s) <= n else s[:n] + "\n…[tronqué]"


class DockerSandbox:
    isolation = "docker"

    def __init__(self, cfg, work_root: Path):
        self.cfg, self.work_root = cfg, work_root
        self._available: bool | None = None
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def available(self) -> bool:
        if self._available is None:
            ok = False
            if shutil.which("docker"):
                try:
                    ok = subprocess.run(["docker", "image", "inspect", self.cfg.image], capture_output=True, timeout=15).returncode == 0
                except (subprocess.SubprocessError, OSError):
                    ok = False
            self._available = ok
        return self._available

    def run(self, code: str, stdin: str = "", timeout: int | None = None) -> SandboxResult:
        timeout = timeout or self.cfg.timeout_s
        name = f"orch-{uuid.uuid4().hex[:12]}"
        work = self.work_root / name
        work.mkdir(parents=True)
        try:
            (work / "main.py").write_text(code, encoding="utf-8")
            (work / "stdin.txt").write_text(stdin, encoding="utf-8")
            os.chmod(work, 0o777)
            cmd = ["docker", "run", "--rm", "--name", name, "--label", LABEL,
                   "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--user", "1000:1000", "--cpus", str(self.cfg.cpus), "--memory", self.cfg.memory,
                   "--pids-limit", str(self.cfg.pids_limit), "-v", f"{work}:/work", "-w", "/work",
                   self.cfg.image, "sh", "-c", "python /work/main.py < /work/stdin.txt"]
            with self._lock:
                self._running.add(name)
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
                killed = r.returncode == 137
                return SandboxResult(r.returncode, _clip(r.stdout), _clip(r.stderr), False, self.isolation, killed)
            except subprocess.TimeoutExpired:
                subprocess.run(["docker", "kill", name], capture_output=True)
                return SandboxResult(-1, "", f"délai dépassé ({timeout}s)", True, self.isolation)
            finally:
                with self._lock:
                    self._running.discard(name)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def kill_all(self) -> int:
        try:
            ids = subprocess.run(["docker", "ps", "-q", "--filter", f"label={LABEL}"], capture_output=True, text=True, timeout=5).stdout.split()
        except (subprocess.SubprocessError, OSError):
            return 0
        if ids:
            subprocess.run(["docker", "kill", *ids], capture_output=True, timeout=10)
        return len(ids)


class SubprocessSandbox:
    """Repli sans Docker : dossier temporaire, environnement vidé, délai maximal. Isolation DÉGRADÉE."""

    isolation = "degradee"

    def __init__(self, cfg, work_root: Path):
        self.cfg, self.work_root = cfg, work_root
        self._procs: set[subprocess.Popen] = set()
        self._lock = threading.Lock()

    def available(self) -> bool:
        return True

    def run(self, code: str, stdin: str = "", timeout: int | None = None) -> SandboxResult:
        timeout = timeout or self.cfg.timeout_s
        work = self.work_root / f"sub-{uuid.uuid4().hex[:12]}"
        work.mkdir(parents=True)
        try:
            (work / "main.py").write_text(code, encoding="utf-8")
            env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8", "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
            p = subprocess.Popen([sys.executable, "-I", "main.py"], cwd=work, env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            with self._lock:
                self._procs.add(p)
            try:
                out, err = p.communicate(stdin, timeout=timeout)
                return SandboxResult(p.returncode, _clip(out), _clip(err), False, self.isolation, p.returncode < 0)
            except subprocess.TimeoutExpired:
                p.kill()
                p.communicate()
                return SandboxResult(-1, "", f"délai dépassé ({timeout}s)", True, self.isolation)
            finally:
                with self._lock:
                    self._procs.discard(p)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def kill_all(self) -> int:
        with self._lock:
            procs = list(self._procs)
        for p in procs:
            try:
                p.kill()
            except OSError:
                pass
        return len(procs)


class Sandbox:
    """Choisit Docker si disponible, sinon le repli ; journalise le niveau d'isolation."""

    def __init__(self, p):
        self.p = p
        work_root = p.data_dir / "sandbox"
        work_root.mkdir(parents=True, exist_ok=True)
        self.docker = DockerSandbox(p.cfg.runtime, work_root)
        self.fallback = SubprocessSandbox(p.cfg.runtime, work_root)
        self._warned = False

    def backend(self):
        if self.p.cfg.runtime.prefer_docker and self.docker.available():
            return self.docker
        if not self._warned:
            self._warned = True
            self.p.alerts.raise_("isolation_degradee", "Docker indisponible : exécution en sous-processus (isolation dégradée)", gravite="attention")
        return self.fallback

    def run(self, code: str, *, actor_id: str | None = None, niveau: str | None = None, stdin: str = "",
            timeout: int | None = None, correlation_id: str | None = None, label: str = "executer_code") -> SandboxResult:
        if self.p.emergency.active:
            return SandboxResult(-1, "", "arrêt d'urgence actif", False, "aucune", True)
        be = self.backend()
        res = be.run(code, stdin=stdin, timeout=timeout)
        self.p.audit.record("action", label, agent_id=actor_id, niveau=niveau, cible="sandbox",
                            resultat="ok" if res.ok else f"echec (code {res.returncode})",
                            correlation_id=correlation_id,
                            details={"isolation": res.isolation, "timed_out": res.timed_out, "stderr": res.stderr[-500:]})
        return res

    def kill_all(self) -> int:
        return self.docker.kill_all() + self.fallback.kill_all()
