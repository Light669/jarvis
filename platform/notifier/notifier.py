"""Notifier Windows d'Orchestra (tourne sur l'hôte, lancé par start.ps1).

Les conteneurs ne peuvent pas afficher de notification Windows : ce petit processus écoute le flux
d'alertes de l'API locale (WebSocket authentifié) et affiche un toast pour chaque alerte
« attention », « grave » ou « critique ». Sans Windows, il écrit l'alerte sur la sortie standard
(ou utilise notify-send sous Linux).
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEVELS = {"attention", "grave", "critique"}
ICONS = {"attention": "⚠️", "grave": "🔴", "critique": "🚨"}


def read_token() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ORCHESTRA_TOKEN="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("ORCHESTRA_TOKEN", "")


def read_port() -> int:
    try:
        return int(yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["server"]["port"])
    except Exception:
        return 8765


def toast(title: str, message: str) -> None:
    if platform.system() == "Windows":
        try:
            from win11toast import notify  # type: ignore

            notify(title, message, app_id="Orchestra")
            return
        except Exception:
            pass
        # repli sans dépendance : API WinRT via PowerShell
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
            "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            "$x = $t.GetElementsByTagName('text');"
            f"$x.Item(0).AppendChild($t.CreateTextNode({json.dumps(title)})) > $null;"
            f"$x.Item(1).AppendChild($t.CreateTextNode({json.dumps(message)})) > $null;"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Orchestra').Show([Windows.UI.Notifications.ToastNotification]::new($t))"
        )
        subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], capture_output=True)
        return
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", title, message], capture_output=True)
    print(f"[ALERTE] {title} — {message}", flush=True)


def format_alert(event: dict) -> tuple[str, str] | None:
    if event.get("type") != "alert" or event.get("gravite") not in LEVELS:
        return None
    return f"{ICONS[event['gravite']]} Orchestra — {event['gravite']}", str(event.get("message", ""))[:250]


async def run() -> None:
    import websockets

    url = f"ws://127.0.0.1:{read_port()}/ws?token={read_token()}"
    delay = 1
    while True:
        try:
            async with websockets.connect(url, max_size=2**20) as ws:
                delay = 1
                async for raw in ws:
                    alert = format_alert(json.loads(raw))
                    if alert:
                        toast(*alert)
        except Exception:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


if __name__ == "__main__":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    asyncio.run(run())
