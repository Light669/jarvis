"""Bus d'événements temps réel (WebSocket du tableau de bord, notifier)."""
from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import Any

from orchestra.models import now_iso


class EventBus:
    def __init__(self, history: int = 500):
        self._subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()
        self.recent: deque[dict[str, Any]] = deque(maxlen=history)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subs.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs = [(l, s) for l, s in self._subs if s is not q]

    def publish(self, event_type: str, /, **data: Any) -> dict[str, Any]:
        """Utilisable depuis n'importe quel thread."""
        event = {"type": event_type, "ts": now_iso(), **data}
        self.recent.append(event)
        with self._lock:
            subs = list(self._subs)
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(_put, q, event)
            except RuntimeError:  # boucle fermée
                self.unsubscribe(q)
        return event


def _put(q: asyncio.Queue, event: dict[str, Any]) -> None:
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    q.put_nowait(event)
