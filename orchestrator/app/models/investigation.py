"""Investigation data models for the orchestrator."""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InvestigationStatus(str, Enum):
    QUEUED = "QUEUED"
    INVESTIGATING = "INVESTIGATING"
    INVESTIGATION_COMPLETE = "INVESTIGATION_COMPLETE"
    LAUNCHING = "LAUNCHING"
    FIX_IN_PROGRESS = "FIX_IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW"  # Fix PR created, awaiting manual approval
    RESOLVED = "RESOLVED"
    ROUTED = "ROUTED"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class InvestigationClassification(str, Enum):
    AUTO_FIX = "AUTO_FIX"          # Auto-fixable, high confidence
    NEEDS_REVIEW = "NEEDS_REVIEW"  # Human review needed
    ESCALATE = "ESCALATE"          # Senior decision required


class TelemetryStep(BaseModel):
    """A single step in the investigation/fix telemetry timeline."""
    id: str
    label: str
    status: str = "pending"  # pending, in_progress, completed, failed
    timestamp: Optional[float] = None
    detail: Optional[str] = None


class InvestigationReport(BaseModel):
    """Structured output from Devin's investigation."""
    relevant_files: list[str] = Field(default_factory=list)
    git_history: list[str] = Field(default_factory=list)
    root_cause: str = ""
    complexity: str = ""  # low, medium, high
    fix_confidence: int = 0  # 1-100
    related_issues: list[int] = Field(default_factory=list)
    classification: Optional[InvestigationClassification] = None
    summary: str = ""
    recommended_fix: str = ""


class Investigation(BaseModel):
    """An investigation representing a GitHub issue under investigation."""
    id: str
    issue_number: int
    issue_title: str
    issue_body: str
    issue_url: str
    issue_labels: list[str] = Field(default_factory=list)
    status: InvestigationStatus = InvestigationStatus.QUEUED
    classification: Optional[InvestigationClassification] = None
    devin_session_id: Optional[str] = None
    devin_session_url: Optional[str] = None
    fix_session_id: Optional[str] = None
    investigation_report: Optional[InvestigationReport] = None
    telemetry: list[TelemetryStep] = Field(default_factory=list)
    playbook_name: Optional[str] = None
    playbook_id: Optional[str] = None
    pr_url: Optional[str] = None
    priority: int = 50  # 0-100, higher = more urgent
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    elapsed_seconds: Optional[float] = None
    error: Optional[str] = None

    def get_investigation_telemetry(self) -> list[TelemetryStep]:
        """Return the standard investigation telemetry steps."""
        return [
            TelemetryStep(id="ingest", label="Issue Ingested"),
            TelemetryStep(id="scan", label="Codebase Scan"),
            TelemetryStep(id="files", label="Files Identified"),
            TelemetryStep(id="git", label="Git History Traced"),
            TelemetryStep(id="root_cause", label="Root Cause Analysis"),
            TelemetryStep(id="classify", label="Issue Classified"),
        ]

    def get_fix_telemetry(self) -> list[TelemetryStep]:
        """Return the standard fix-phase telemetry steps."""
        return [
            TelemetryStep(id="fix_start", label="Writing Fix"),
            TelemetryStep(id="pr_open", label="Opening PR"),
            TelemetryStep(id="resolved", label="Resolved"),
        ]


class SSEEvent(BaseModel):
    """An event sent to the dashboard via SSE."""
    event_type: str  # investigation_created, telemetry_update, investigation_complete, investigation_resolved, etc.
    investigation_id: str
    data: dict = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class DashboardState(BaseModel):
    """Full dashboard state for initial load."""
    investigations: dict[str, Investigation] = Field(default_factory=dict)
    stats: dict = Field(default_factory=dict)
    uptime_start: float = Field(default_factory=time.time)
