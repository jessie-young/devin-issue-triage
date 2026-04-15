"""Event bus for SSE streaming to the dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from app.models.investigation import SSEEvent

logger = logging.getLogger(__name__)


class EventBus:
    """In-memory event bus that fans out SSE events to connected clients."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[SSEEvent]] = []
        self._history: list[SSEEvent] = []
        self._max_history = 500

    async def publish(self, event: SSEEvent) -> None:
        """Publish an event to all subscribers and store in history."""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        dead: list[asyncio.Queue[SSEEvent]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)

        for q in dead:
            self._subscribers.remove(q)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribe to the event stream. Yields SSE-formatted strings."""
        q: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        try:
            while True:
                event = await q.get()
                data = event.model_dump_json()
                yield f"event: {event.event_type}\ndata: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def get_recent_events(self, limit: int = 100) -> list[SSEEvent]:
        """Return recent events for telemetry strip."""
        return self._history[-limit:]


# Singleton
event_bus = EventBus()
