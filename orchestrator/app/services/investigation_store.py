"""In-memory investigation store."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from app.models.investigation import (
    DashboardState,
    Investigation,
    InvestigationClassification,
    InvestigationStatus,
    SSEEvent,
)
from app.services.event_bus import event_bus


class InvestigationStore:
    """Manages all investigations in memory."""

    def __init__(self) -> None:
        self._investigations: dict[str, Investigation] = {}
        self._uptime_start: float = time.time()
        self._auto_triage: bool = False

    @property
    def auto_triage(self) -> bool:
        return self._auto_triage

    @auto_triage.setter
    def auto_triage(self, value: bool) -> None:
        self._auto_triage = value

    async def create_investigation(
        self,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        issue_url: str,
        issue_labels: list[str] | None = None,
    ) -> Investigation:
        """Create a new investigation from a GitHub issue."""
        investigation_id = f"FINSERV-{issue_number}"
        if investigation_id in self._investigations:
            return self._investigations[investigation_id]

        investigation = Investigation(
            id=investigation_id,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            issue_url=issue_url,
            issue_labels=issue_labels or [],
            status=InvestigationStatus.QUEUED,
        )
        investigation.telemetry = investigation.get_investigation_telemetry()
        self._investigations[investigation_id] = investigation

        await event_bus.publish(SSEEvent(
            event_type="investigation_created",
            investigation_id=investigation_id,
            data={"issue_number": issue_number, "title": issue_title, "status": "QUEUED"},
        ))

        return investigation

    async def update_investigation(self, investigation_id: str, **kwargs) -> Optional[Investigation]:
        """Update an investigation's fields and broadcast the change."""
        investigation = self._investigations.get(investigation_id)
        if not investigation:
            return None

        for key, value in kwargs.items():
            if hasattr(investigation, key):
                setattr(investigation, key, value)

        await event_bus.publish(SSEEvent(
            event_type="investigation_updated",
            investigation_id=investigation_id,
            data=kwargs,
        ))

        return investigation

    async def update_telemetry_step(
        self,
        investigation_id: str,
        step_id: str,
        status: str,
        detail: str | None = None,
    ) -> None:
        """Update a specific telemetry step on an investigation."""
        investigation = self._investigations.get(investigation_id)
        if not investigation:
            return

        for step in investigation.telemetry:
            if step.id == step_id:
                step.status = status
                step.timestamp = time.time()
                if detail:
                    step.detail = detail
                break

        await event_bus.publish(SSEEvent(
            event_type="telemetry_update",
            investigation_id=investigation_id,
            data={"step_id": step_id, "status": status, "detail": detail},
        ))

    async def clear_all(self) -> int:
        """Clear all investigations and reset uptime. Returns count of cleared items."""
        count = len(self._investigations)
        self._investigations.clear()
        self._uptime_start = time.time()

        await event_bus.publish(SSEEvent(
            event_type="investigations_cleared",
            investigation_id="SYSTEM",
            data={"cleared": count},
        ))

        return count

    def get_investigation(self, investigation_id: str) -> Optional[Investigation]:
        return self._investigations.get(investigation_id)

    def get_all_investigations(self) -> list[Investigation]:
        return list(self._investigations.values())

    def get_investigations_by_status(self, status: InvestigationStatus) -> list[Investigation]:
        return [inv for inv in self._investigations.values() if inv.status == status]

    def get_dashboard_state(self) -> DashboardState:
        """Return full state for dashboard initial load."""
        active = len([inv for inv in self._investigations.values() if inv.status in (
            InvestigationStatus.INVESTIGATING, InvestigationStatus.INVESTIGATION_COMPLETE,
            InvestigationStatus.FIX_IN_PROGRESS, InvestigationStatus.LAUNCHING,
        )])
        completed = len([inv for inv in self._investigations.values() if inv.status in (
            InvestigationStatus.RESOLVED, InvestigationStatus.ROUTED, InvestigationStatus.CLOSED
        )])
        queued = len([inv for inv in self._investigations.values() if inv.status == InvestigationStatus.QUEUED])

        # Resolved today: completed investigations whose completed_at falls on today (UTC)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        resolved_today = len([inv for inv in self._investigations.values()
            if inv.status in (InvestigationStatus.RESOLVED, InvestigationStatus.ROUTED, InvestigationStatus.CLOSED)
            and inv.completed_at is not None and inv.completed_at >= today_start
        ])

        return DashboardState(
            investigations=self._investigations,
            stats={
                "active": active,
                "completed": completed,
                "queued": queued,
                "total": len(self._investigations),
                "resolved_today": resolved_today,
                "auto_fix_count": len([inv for inv in self._investigations.values() if inv.classification == InvestigationClassification.AUTO_FIX]),
                "needs_review_count": len([inv for inv in self._investigations.values() if inv.classification == InvestigationClassification.NEEDS_REVIEW]),
                "escalate_count": len([inv for inv in self._investigations.values() if inv.classification == InvestigationClassification.ESCALATE]),
            },
            uptime_start=self._uptime_start,
        )


# Singleton
investigation_store = InvestigationStore()
