"""In-memory mission store."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from app.models.mission import (
    DashboardState,
    Mission,
    MissionClassification,
    MissionStatus,
    SSEEvent,
)
from app.services.event_bus import event_bus


class MissionStore:
    """Manages all missions in memory."""

    def __init__(self) -> None:
        self._missions: dict[str, Mission] = {}
        self._uptime_start: float = time.time()

    async def create_mission(
        self,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        issue_url: str,
        issue_labels: list[str] | None = None,
    ) -> Mission:
        """Create a new mission from a GitHub issue."""
        mission_id = f"FINSERV-{issue_number}"
        if mission_id in self._missions:
            return self._missions[mission_id]

        mission = Mission(
            id=mission_id,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            issue_url=issue_url,
            issue_labels=issue_labels or [],
            status=MissionStatus.QUEUED,
        )
        mission.telemetry = mission.get_investigation_telemetry()
        self._missions[mission_id] = mission

        await event_bus.publish(SSEEvent(
            event_type="mission_created",
            mission_id=mission_id,
            data={"issue_number": issue_number, "title": issue_title, "status": "QUEUED"},
        ))

        return mission

    async def update_mission(self, mission_id: str, **kwargs) -> Optional[Mission]:
        """Update a mission's fields and broadcast the change."""
        mission = self._missions.get(mission_id)
        if not mission:
            return None

        for key, value in kwargs.items():
            if hasattr(mission, key):
                setattr(mission, key, value)

        await event_bus.publish(SSEEvent(
            event_type="mission_updated",
            mission_id=mission_id,
            data=kwargs,
        ))

        return mission

    async def update_telemetry_step(
        self,
        mission_id: str,
        step_id: str,
        status: str,
        detail: str | None = None,
    ) -> None:
        """Update a specific telemetry step on a mission."""
        mission = self._missions.get(mission_id)
        if not mission:
            return

        for step in mission.telemetry:
            if step.id == step_id:
                step.status = status
                step.timestamp = time.time()
                if detail:
                    step.detail = detail
                break

        await event_bus.publish(SSEEvent(
            event_type="telemetry_update",
            mission_id=mission_id,
            data={"step_id": step_id, "status": status, "detail": detail},
        ))

    def get_mission(self, mission_id: str) -> Optional[Mission]:
        return self._missions.get(mission_id)

    def get_all_missions(self) -> list[Mission]:
        return list(self._missions.values())

    def get_missions_by_status(self, status: MissionStatus) -> list[Mission]:
        return [m for m in self._missions.values() if m.status == status]

    def get_dashboard_state(self) -> DashboardState:
        """Return full state for dashboard initial load."""
        active = len([m for m in self._missions.values() if m.status in (
            MissionStatus.INVESTIGATING, MissionStatus.INVESTIGATION_COMPLETE,
            MissionStatus.FIX_IN_PROGRESS, MissionStatus.LAUNCHING,
        )])
        completed = len([m for m in self._missions.values() if m.status in (
            MissionStatus.MISSION_COMPLETE, MissionStatus.ROUTED, MissionStatus.CLOSED
        )])
        queued = len([m for m in self._missions.values() if m.status == MissionStatus.QUEUED])

        # Resolved today: completed missions whose completed_at falls on today (UTC)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        resolved_today = len([m for m in self._missions.values()
            if m.status in (MissionStatus.MISSION_COMPLETE, MissionStatus.ROUTED, MissionStatus.CLOSED)
            and m.completed_at is not None and m.completed_at >= today_start
        ])

        return DashboardState(
            missions=self._missions,
            stats={
                "active": active,
                "completed": completed,
                "queued": queued,
                "total": len(self._missions),
                "resolved_today": resolved_today,
                "strike_count": len([m for m in self._missions.values() if m.classification == MissionClassification.STRIKE]),
                "assist_count": len([m for m in self._missions.values() if m.classification == MissionClassification.ASSIST]),
                "command_count": len([m for m in self._missions.values() if m.classification == MissionClassification.COMMAND]),
            },
            uptime_start=self._uptime_start,
        )


# Singleton
mission_store = MissionStore()
