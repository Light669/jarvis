"""MVP : organisation de démonstration + simulation (tout passe par les vrais services)."""
from orchestra.demo import seed
from orchestra.models import OWNER


def test_demo_simulation_brings_org_to_life(plat):
    plat.cfg.runtime.prefer_docker = False
    seed(plat)
    assert plat.simulation.active
    plat.simulation.rng.seed(7)
    for _ in range(150):
        plat.simulation.tick()
        for t in list(plat.runtime._threads.values()):
            t.join(10)
    count = lambda sql: plat.db.scalar(sql)  # noqa: E731
    assert count("SELECT COUNT(*) FROM tasks WHERE statut='terminee'") >= 20
    assert count("SELECT COUNT(*) FROM tasks WHERE succes IS NOT NULL") >= 5
    assert count("SELECT COUNT(*) FROM messages WHERE sujet='Compte rendu'") >= 10  # le modèle démo rend compte
    assert count("SELECT COUNT(*) FROM requests WHERE statut IN ('acceptee','refusee')") >= 1
    assert count("SELECT COUNT(*) FROM log_index WHERE type_evenement='permission_refusee'") >= 1
    assert count("SELECT COUNT(*) FROM learnings") >= 20
    assert count("SELECT COUNT(*) FROM tasks WHERE statut='erreur'") == 0
    assert plat.verify_logs().ok


def test_simulation_respects_pause_and_emergency(plat):
    seed(plat)
    plat.simulation.set_active(False)
    assert plat.simulation.tick() is None
    plat.simulation.set_active(True)
    plat.emergency.stop(OWNER, "test")
    assert plat.simulation.tick() is None
    plat.emergency.resume(OWNER)


def test_simulation_api_toggle(plat):
    from fastapi.testclient import TestClient
    from orchestra.api.app import create_app
    H = {"Authorization": "Bearer test-token-0123456789"}
    with TestClient(create_app(platform=plat, background=False)) as c:
        assert c.get("/api/overview", headers=H).json()["simulation"] is None  # pas une démo
        seed(plat)
        assert c.get("/api/overview", headers=H).json()["simulation"] is True
        c.post("/api/simulation", json={"active": False}, headers=H)
        assert c.get("/api/overview", headers=H).json()["simulation"] is False
