"""Mission data models for the orchestrator."""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MissionStatus(str, Enum):
    QUEUED = "QUEUED"
    INVESTIGATING = "INVESTIGATING"
    INVESTIGATION_COMPLETE = "INVESTIGATION_COMPLETE"
    LAUNCHING = "LAUNCHING"
    FIX_IN_PROGRESS = "FIX_IN_PROGRESS"
    MISSION_COMPLETE = "MISSION_COMPLETE"
    ROUTED = "ROUTED"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class MissionClassification(str, Enum):
    STRIKE = "STRIKE"      # Auto-fixable, high confidence
    ASSIST = "ASSIST"      # Human needed with Devin briefing
    COMMAND = "COMMAND"     # Senior decision required


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
    classification: Optional[MissionClassification] = None
    summary: str = ""
    recommended_fix: str = ""


class Mission(BaseModel):
    """A mission representing a GitHub issue under investigation."""
    id: str
    issue_number: int
    issue_title: str
    issue_body: str
    issue_url: str
    issue_labels: list[str] = Field(default_factory=list)
    status: MissionStatus = MissionStatus.QUEUED
    classification: Optional[MissionClassification] = None
    devin_session_id: Optional[str] = None
    fix_session_id: Optional[str] = None
    investigation_report: Optional[InvestigationReport] = None
    telemetry: list[TelemetryStep] = Field(default_factory=list)
    pr_url: Optional[str] = None
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
            TelemetryStep(id="classify", label="Mission Classified"),
        ]

    def get_fix_telemetry(self) -> list[TelemetryStep]:
        """Return the standard fix-phase telemetry steps."""
        return [
            TelemetryStep(id="fix_start", label="Writing Fix"),
            TelemetryStep(id="test_write", label="Writing Regression Test"),
            TelemetryStep(id="test_run", label="Running Test Suite"),
            TelemetryStep(id="pr_open", label="Opening PR"),
            TelemetryStep(id="mission_complete", label="MISSION COMPLETE"),
        ]


class SSEEvent(BaseModel):
    """An event sent to the dashboard via SSE."""
    event_type: str  # mission_created, telemetry_update, investigation_complete, mission_complete, etc.
    mission_id: str
    data: dict = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class DashboardState(BaseModel):
    """Full dashboard state for initial load."""
    missions: dict[str, Mission] = Field(default_factory=dict)
    stats: dict = Field(default_factory=dict)
    uptime_start: float = Field(default_factory=time.time)
