"""Phase 6 : recette du tableau de bord dans un vrai navigateur (Chromium + Playwright).

Lance l'API réelle (uvicorn) sur un port libre, avec l'organisation de démonstration.
Ignoré si Playwright, Chromium ou le build du tableau de bord sont absents.
"""
import os
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "platform" / "dashboard" / "dist" / "index.html"
CHROME = next((p for p in [os.environ.get("CHROMIUM_PATH"), "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"] if p and Path(p).exists()), None)

pw = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not DIST.exists(), reason="tableau de bord non construit (npm run build)")


@pytest.fixture()
def server(root):
    import uvicorn

    from orchestra.api.app import create_app
    from orchestra.demo import seed
    from orchestra.platform import Platform

    p = Platform(root)
    seed(p)
    app = create_app(platform=p, background=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", p
    srv.should_exit = True
    th.join(10)
    p.close()


def test_dashboard_end_to_end(server, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    base, plat = server
    errors = []
    with sync_playwright() as pwr:
        browser = pwr.chromium.launch(executable_path=CHROME) if CHROME else pwr.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))

        # jeton obligatoire
        page.goto(base + "/")
        page.get_by_label("Jeton local").fill("faux")
        page.get_by_role("button", name="Se connecter").click()
        expect(page.get_by_text("Jeton invalide")).to_be_visible()

        page.goto(base + "/#token=test-token-0123456789")
        expect(page.get_by_test_id("node-agent-0001")).to_be_visible(timeout=10000)
        assert page.locator(".react-flow__edge.peer").count() >= 1  # liens entre pairs en pointillés

        # clic sur un agent : panneau latéral + modification versionnée
        page.get_by_test_id("node-agent-0004").click()
        expect(page.get_by_test_id("agent-panel")).to_be_visible()
        page.locator("[data-testid=agent-panel] textarea").nth(2).fill("Consigne modifiée depuis la carte")
        page.get_by_test_id("save-agent").click()
        expect(page.get_by_test_id("node-agent-0004")).to_contain_text("v2", timeout=5000)
        assert plat.agents.get("agent-0004")["instructions"] == "Consigne modifiée depuis la carte"
        assert (plat.vault_dir / "Agents/Salaries/prospecteur.md").read_text(encoding="utf-8").count("Consigne modifiée depuis la carte") == 1
        for tab in ["Activité", "Messages", "Skills", "Historique", "Coûts", "Fiche"]:
            page.get_by_role("tab", name=tab).click()
        page.get_by_label("Fermer le panneau").click()

        # formulaire « Nouvel agent » -> nœud sur la carte + fiche dans le coffre
        page.get_by_test_id("new-agent").click()
        page.get_by_role("dialog").get_by_placeholder("Prospecteur").fill("Analyste Data")
        page.locator("[role=dialog] input").nth(1).fill("demo/echo")
        selects = page.locator("[role=dialog] select")
        selects.nth(0).select_option("salarie")
        selects.nth(1).select_option("agent-0003")
        page.get_by_test_id("create-agent").click()
        expect(page.get_by_test_id("node-agent-0009")).to_be_visible(timeout=5000)
        assert (plat.vault_dir / "Agents/Salaries/analyste-data.md").exists()

        # une tâche fait « pulser » puis revenir l'agent ; les messages animent les liens
        page.get_by_placeholder("Ex. : Liste 10 PME").fill("Analyser les ventes")
        page.get_by_role("button", name="Lancer").click()
        for _ in range(50):
            t = plat.db.one("SELECT statut FROM tasks WHERE agent_id='agent-0009'")
            if t and t["statut"] == "terminee":
                break
            time.sleep(0.1)
        assert t["statut"] == "terminee"
        page.get_by_label("Fermer le panneau").click()

        # pages
        for nav, text in [("demandes", "Accès à la recherche web"), ("skills", "Skills"), ("budget", "Dépensé ce mois"),
                          ("logs", "modification_fiche"), ("alertes", "Alertes")]:
            page.get_by_test_id(f"nav-{nav}").click()
            expect(page.get_by_text(text).first).to_be_visible(timeout=5000)

        # arrêt d'urgence depuis n'importe quelle page, en moins de 5 s
        t0 = time.monotonic()
        page.get_by_test_id("emergency-stop").click()
        page.get_by_test_id("emergency-confirm").click()
        expect(page.get_by_text("ARRÊT D'URGENCE ACTIF")).to_be_visible(timeout=5000)
        assert time.monotonic() - t0 < 5 and plat.emergency.active
        page.get_by_test_id("emergency-resume").click()
        expect(page.get_by_test_id("emergency-stop")).to_be_visible(timeout=5000)
        assert not plat.emergency.active
        page.screenshot(path=str(tmp_path / "carte.png"))
        browser.close()
    assert not errors, errors
    # chaque action du tableau de bord est journalisée
    assert plat.db.query("SELECT * FROM log_index WHERE type_evenement='tableau_de_bord' AND action LIKE 'POST /api/emergency%'")
