"""Investigation management endpoints and SSE streaming."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.models.investigation import InvestigationClassification, InvestigationReport, InvestigationStatus, SSEEvent
from app.services.devin_client import devin_client
from app.services.event_bus import event_bus
from app.services.github_service import github_service
from app.services.investigation_store import investigation_store
from app.services.session_poller import session_poller

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/investigations", tags=["investigations"])


class FileInvestigationRequest(BaseModel):
    """Request to manually file an investigation from an issue URL or number."""
    issue_url: str | None = None
    issue_number: int | None = None


class LaunchFixRequest(BaseModel):
    """Request to launch a fix for an AUTO_FIX investigation."""
    investigation_id: str


class RouteRequest(BaseModel):
    """Request to route a NEEDS_REVIEW or ESCALATE investigation."""
    investigation_id: str
    action: str = "route"  # route, dismiss


@router.get("/")
async def list_investigations():
    """List all investigations."""
    investigations = investigation_store.get_all_investigations()
    return {"investigations": [inv.model_dump() for inv in investigations]}


@router.get("/state")
async def get_dashboard_state():
    """Get full dashboard state for initial load."""
    state = investigation_store.get_dashboard_state()
    return state.model_dump()


@router.get("/events")
async def get_recent_events(limit: int = 100):
    """Get recent telemetry events for the strip."""
    events = event_bus.get_recent_events(limit)
    return {"events": [e.model_dump() for e in events]}


@router.get("/stream")
async def sse_stream():
    """SSE endpoint for real-time dashboard updates."""
    return EventSourceResponse(event_bus.subscribe())


@router.post("/reset")
async def reset_investigations():
    """Clear all investigations and reset the dashboard, then seed demo data.

    Used to restart the demo from a clean slate. The in-memory store is
    wiped, then 4 pre-investigated items are seeded into "In Progress"
    (INVESTIGATION_COMPLETE) so the board always has realistic data to demo
    the "initial backlog triage" capability. New live issues filed via webhook
    will appear alongside these seed items.
    """
    cleared = await investigation_store.clear_all()
    seeded = await _seed_demo_investigations()
    return {"status": "ok", "cleared": cleared, "seeded": seeded}


@router.get("/{investigation_id}")
async def get_investigation(investigation_id: str):
    """Get a single investigation by ID."""
    investigation = investigation_store.get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation.model_dump()


@router.post("/file")
async def file_investigation(req: FileInvestigationRequest):
    """Manually file an investigation from an issue URL or number."""
    issue_number = req.issue_number
    if req.issue_url and not issue_number:
        # Extract issue number from URL
        import re
        match = re.search(r"/issues/(\d+)", req.issue_url)
        if match:
            issue_number = int(match.group(1))

    if not issue_number:
        raise HTTPException(status_code=400, detail="Provide issue_url or issue_number")

    # Fetch issue details from GitHub
    issue = await github_service.get_issue(issue_number)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Issue #{issue_number} not found")

    issue_title = issue.get("title", "")
    issue_body = issue.get("body", "")
    issue_url = issue.get("html_url", "")
    issue_labels = [l.get("name", "") for l in issue.get("labels", [])]

    # Create investigation
    investigation = await investigation_store.create_investigation(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        issue_url=issue_url,
        issue_labels=issue_labels,
    )

    # Detect issue type and resolve playbook
    from app.services.playbook_router import playbook_router as _pb_router
    _issue_type, _playbook_id, _playbook_name = _pb_router.resolve_playbook(issue_title, issue_labels)
    await investigation_store.update_investigation(
        investigation.id,
        playbook_name=_playbook_name,
        playbook_id=_playbook_id,
    )

    # Kick off investigation
    try:
        session = await devin_client.create_investigation_session(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            repo=settings.target_repo,
            playbook_id=_playbook_id,
            issue_type=_issue_type.value,
        )
        session_id = session.get("session_id") or session.get("id", "")

        await investigation_store.update_investigation(
            investigation.id,
            status=InvestigationStatus.INVESTIGATING,
            devin_session_id=session_id,
            started_at=time.time(),
        )
        await investigation_store.update_telemetry_step(investigation.id, "ingest", "completed")

        # Start polling
        await session_poller.start_polling(investigation.id, session_id, "investigation")

        return {"status": "accepted", "investigation_id": investigation.id, "session_id": session_id}

    except Exception as e:
        logger.error(f"Failed to create investigation session: {e}")
        await investigation_store.update_investigation(
            investigation.id,
            status=InvestigationStatus.FAILED,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/launch")
async def launch_fix(req: LaunchFixRequest):
    """Apply fix — create a fix session for an AUTO_FIX investigation."""
    investigation = investigation_store.get_investigation(req.investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    if investigation.status != InvestigationStatus.INVESTIGATION_COMPLETE:
        raise HTTPException(
            status_code=400,
            detail=f"Investigation is in state {investigation.status.value}, expected INVESTIGATION_COMPLETE",
        )

    if investigation.classification != InvestigationClassification.AUTO_FIX:
        raise HTTPException(
            status_code=400,
            detail=f"Only AUTO_FIX investigations can be auto-fixed. This investigation is {investigation.classification}",
        )

    report = investigation.investigation_report
    if not report:
        raise HTTPException(status_code=400, detail="No investigation report available")

    # Transition to fix phase
    fix_telemetry = investigation.get_fix_telemetry()
    await investigation_store.update_investigation(
        req.investigation_id,
        status=InvestigationStatus.LAUNCHING,
        telemetry=fix_telemetry,
        started_at=time.time(),
    )

    try:
        session = await devin_client.create_fix_session(
            issue_number=investigation.issue_number,
            issue_title=investigation.issue_title,
            issue_body=investigation.issue_body,
            repo=settings.target_repo,
            investigation_summary=report.summary,
            root_cause=report.root_cause,
            recommended_fix=report.recommended_fix,
        )
        session_id = session.get("session_id") or session.get("id", "")

        await investigation_store.update_investigation(
            req.investigation_id,
            status=InvestigationStatus.FIX_IN_PROGRESS,
            fix_session_id=session_id,
        )

        # Start polling fix session
        await session_poller.start_polling(req.investigation_id, session_id, "fix")

        return {"status": "launched", "investigation_id": req.investigation_id, "session_id": session_id}

    except Exception as e:
        logger.error(f"Failed to create fix session: {e}")
        await investigation_store.update_investigation(
            req.investigation_id,
            status=InvestigationStatus.FAILED,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/route")
async def route_investigation(req: RouteRequest):
    """Route a NEEDS_REVIEW or ESCALATE investigation to the Resolved column."""
    investigation = investigation_store.get_investigation(req.investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    if investigation.status != InvestigationStatus.INVESTIGATION_COMPLETE:
        raise HTTPException(
            status_code=400,
            detail=f"Investigation is in state {investigation.status.value}, expected INVESTIGATION_COMPLETE",
        )

    if investigation.classification not in (
        InvestigationClassification.NEEDS_REVIEW,
        InvestigationClassification.ESCALATE,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Only NEEDS_REVIEW or ESCALATE investigations can be routed. This is {investigation.classification}",
        )

    await investigation_store.update_investigation(
        req.investigation_id,
        status=InvestigationStatus.ROUTED,
        completed_at=time.time(),
    )

    await event_bus.publish(
        SSEEvent(
            event_type="investigation_resolved",
            investigation_id=req.investigation_id,
            data={"action": req.action},
        )
    )

    return {"status": "routed", "investigation_id": req.investigation_id, "action": req.action}


class ApproveRequest(BaseModel):
    investigation_id: str


@router.post("/approve")
async def approve_investigation(req: ApproveRequest):
    """Approve a PENDING_REVIEW investigation and move it to Resolved."""
    investigation = investigation_store.get_investigation(req.investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    if investigation.status != InvestigationStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Investigation is in state {investigation.status.value}, expected PENDING_REVIEW",
        )

    await investigation_store.update_investigation(
        req.investigation_id,
        status=InvestigationStatus.RESOLVED,
        completed_at=time.time(),
    )

    await event_bus.publish(
        SSEEvent(
            event_type="investigation_resolved",
            investigation_id=req.investigation_id,
            data={"action": "approved"},
        )
    )

    return {"status": "resolved", "investigation_id": req.investigation_id}


@router.post("/ingest-all")
async def ingest_all_issues():
    """Ingest all open issues from the target repo.
    
    Used for pre-seeding the dashboard. Creates investigations without
    starting Devin sessions (for demo purposes with simulated data).
    """
    issues = await github_service.list_issues(state="open", per_page=30)

    created = []
    for issue in issues:
        # Skip pull requests (GitHub API returns PRs in the issues endpoint)
        if "pull_request" in issue:
            continue

        investigation = await investigation_store.create_investigation(
            issue_number=issue["number"],
            issue_title=issue.get("title", ""),
            issue_body=issue.get("body", ""),
            issue_url=issue.get("html_url", ""),
            issue_labels=[l.get("name", "") for l in issue.get("labels", [])],
        )
        created.append(investigation.id)

    return {"status": "ok", "created": len(created), "investigation_ids": created}


@router.post("/investigate-all")
async def investigate_all_queued():
    """Kick off investigations for ALL queued items at once."""
    started_ids = await _start_all_queued()
    return {"status": "ok", "started": len(started_ids), "investigation_ids": started_ids}


async def _start_all_queued() -> list[str]:
    """Start Devin investigations for every QUEUED item. Returns list of started IDs.

    Includes retry with exponential backoff for 429 rate-limit responses.
    """
    queued = investigation_store.get_investigations_by_status(InvestigationStatus.QUEUED)
    if not queued:
        return []

    started: list[str] = []
    for investigation in queued:
        for attempt in range(4):  # up to 4 attempts (initial + 3 retries)
            try:
                session_id = await _start_investigation(investigation)
                started.append(investigation.id)
                break
            except Exception as e:
                is_rate_limit = "429" in str(e)
                if is_rate_limit and attempt < 3:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        "Rate-limited starting %s (attempt %d/4), retrying in %ds",
                        investigation.id, attempt + 1, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Failed to start investigation {investigation.id}: {e}")
                    break

    return started


async def _start_investigation(investigation) -> str:
    """Start a single Devin investigation session for an investigation.

    Resolves the playbook, creates a Devin session, updates the investigation
    status to INVESTIGATING, and starts polling. Returns the session ID.
    """
    from app.services.playbook_router import playbook_router as _pb_router
    _issue_type, _playbook_id, _playbook_name = _pb_router.resolve_playbook(
        investigation.issue_title, investigation.issue_labels
    )
    await investigation_store.update_investigation(
        investigation.id,
        playbook_name=_playbook_name,
        playbook_id=_playbook_id,
    )

    session = await devin_client.create_investigation_session(
        issue_number=investigation.issue_number,
        issue_title=investigation.issue_title,
        issue_body=investigation.issue_body,
        repo=settings.target_repo,
        playbook_id=_playbook_id,
        issue_type=_issue_type.value,
    )
    session_id = session.get("session_id") or session.get("id", "")
    await investigation_store.update_investigation(
        investigation.id,
        status=InvestigationStatus.INVESTIGATING,
        devin_session_id=session_id,
        started_at=time.time(),
    )
    await investigation_store.update_telemetry_step(investigation.id, "ingest", "completed")
    await session_poller.start_polling(investigation.id, session_id, "investigation")
    return session_id


@router.post("/simulate/{investigation_id}")
async def simulate_investigation(investigation_id: str, *, post_comment: bool = True):
    """Simulate an investigation completing (for demo/testing without Devin API).
    
    This populates an investigation with realistic investigation data so the
    dashboard can be demonstrated without needing actual Devin sessions.
    
    Args:
        post_comment: Whether to post the investigation comment to GitHub.
            Set to False during auto-seed to avoid spamming issue comments on every restart.
    """
    import asyncio
    import random

    investigation = investigation_store.get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    # Simulated investigation data based on issue content
    simulations = _get_simulation_data(investigation)
    sim = simulations or _default_simulation(investigation)

    # Update telemetry steps
    for step in investigation.telemetry:
        await investigation_store.update_telemetry_step(
            investigation_id, step.id, "completed", f"Simulated: {step.label}"
        )
        await asyncio.sleep(0.1)

    report = sim["report"]
    classification = report.classification

    await investigation_store.update_investigation(
        investigation_id,
        status=InvestigationStatus.INVESTIGATION_COMPLETE,
        investigation_report=report,
        classification=classification,
        started_at=investigation.created_at,
        completed_at=time.time(),
        elapsed_seconds=random.uniform(120, 480),
    )

    # Post investigation comment to GitHub issue (skip during auto-seed)
    if post_comment:
        try:
            await github_service.post_investigation_comment(
                issue_number=investigation.issue_number,
                investigation_id=investigation_id,
                report=report,
                playbook_name=investigation.playbook_name,
                playbook_id=investigation.playbook_id,
            )
        except Exception as e:
            logger.warning(f"Failed to post investigation comment for {investigation_id}: {e}")

    return {"status": "simulated", "classification": classification.value if classification else "UNKNOWN"}


# Pre-built investigation results for seed issues.  Each entry maps an issue
# number to the data that would have been produced by a completed investigation.
_SEED_INVESTIGATIONS: dict[int, dict] = {
    24: {
        "report": InvestigationReport(
            relevant_files=["src/modules/accounts/service/account.service.ts", "src/modules/accounts/repository/account.repository.ts"],
            git_history=["a3f1d72 — Priya Patel — Nov 5 2025 — Add account balance management with optimistic locking"],
            root_cause="Concurrent withdrawal requests race past the balance check because the read-then-write is not wrapped in a serializable transaction. Two requests can both read the same positive balance and each subtract, resulting in a negative final balance.",
            complexity="high",
            fix_confidence=72,
            classification=InvestigationClassification.NEEDS_REVIEW,
            summary="Race condition in concurrent withdrawals allows negative balance. Needs database-level locking or serializable isolation.",
            recommended_fix="Wrap the balance check and debit in a serializable transaction or use SELECT … FOR UPDATE to lock the row during the withdrawal flow.",
            related_issues=[17],
        ),
        "priority": 90,
    },
    25: {
        "report": InvestigationReport(
            relevant_files=["src/modules/transactions/controller/transaction.controller.ts", "src/modules/transactions/repository/transaction.repository.ts"],
            git_history=["97e21d6 — Marcus Johnson — Nov 18 2025 — Implement transactions module with pagination"],
            root_cause="The search query interpolates the user-supplied query string directly into a SQL LIKE clause without escaping special characters (%, _, \\). When the query contains these characters, the database returns unexpected results or throws a syntax error.",
            complexity="low",
            fix_confidence=94,
            classification=InvestigationClassification.AUTO_FIX,
            summary="Search endpoint fails on special characters due to unescaped SQL LIKE input. Simple sanitization fix.",
            recommended_fix="Escape %, _, and \\ in the query string before passing it to the LIKE clause. Use a parameterized query helper.",
            related_issues=[],
        ),
        "priority": 60,
    },
    26: {
        "report": InvestigationReport(
            relevant_files=["src/modules/auth/service/auth.service.ts", "src/modules/auth/repository/auth.repository.ts"],
            git_history=["f549345 — Sarah Chen — Oct 18 2025 — Implement auth module with JWT token management"],
            root_cause="Password reset tokens are generated with no expiry timestamp. The token validation only checks whether the token exists in the database, never whether it has expired. A leaked reset link remains valid forever.",
            complexity="low",
            fix_confidence=96,
            classification=InvestigationClassification.AUTO_FIX,
            summary="Password reset tokens have no TTL — a leaked link works forever. Add expiry timestamp and validation.",
            recommended_fix="Add an expires_at column to the reset_tokens table, set it to NOW() + 1 hour on creation, and reject tokens where expires_at < NOW().",
            related_issues=[3],
        ),
        "priority": 95,
    },
    27: {
        "report": InvestigationReport(
            relevant_files=["src/modules/payments/service/payment.service.ts", "src/shared/utils/currency.ts"],
            git_history=["91c7038 — Sarah Chen — Oct 13 2025 — Add shared types, currency utils, date helpers"],
            root_cause="Feature request — multi-currency cross-border transfers require FX rate lookup, currency conversion at transfer time, and display of both source and destination amounts. Currently the system only supports single-currency transactions.",
            complexity="high",
            fix_confidence=45,
            classification=InvestigationClassification.ESCALATE,
            summary="Major feature: multi-currency transfers need FX integration, schema changes, and UI work. Architectural decision required.",
            recommended_fix="Integrate an FX rate provider, add source_currency/dest_currency columns to the transfers table, convert at execution time, and show both amounts in the UI.",
            related_issues=[1],
        ),
        "priority": 40,
    },
    28: {
        "report": InvestigationReport(
            relevant_files=["src/modules/notifications/service/notification.service.ts", "src/modules/transactions/service/transaction.service.ts"],
            git_history=["c82e4f1 — Marcus Johnson — Dec 5 2025 — Add notification service scaffolding"],
            root_cause="Feature request — large transaction alerts via email. The notification service exists but has no email transport configured and no trigger wired to the transaction completion flow.",
            complexity="medium",
            fix_confidence=78,
            classification=InvestigationClassification.AUTO_FIX,
            summary="Wire transaction completion event to notification service and add email transport for large-value alerts.",
            recommended_fix="Add a post-transaction hook that emits a 'large_transaction' event when amount exceeds the configurable threshold, and configure the notification service to send emails via SMTP.",
            related_issues=[],
        ),
        "priority": 50,
    },
    29: {
        "report": InvestigationReport(
            relevant_files=["src/shared/middleware/rate-limiter.ts", "src/modules/auth/middleware/auth.middleware.ts"],
            git_history=["b24dc2a — Sarah Chen — Oct 20 2025 — Add auth middleware, error handler, and rate limiter"],
            root_cause="Feature request — per-client API rate limiting. The existing rate limiter uses a global counter, not per-client. Need to key by API token/client ID and enforce configurable limits per tier.",
            complexity="medium",
            fix_confidence=85,
            classification=InvestigationClassification.AUTO_FIX,
            summary="Rate limiter is global, not per-client. Need to key by client ID and add tiered limits.",
            recommended_fix="Replace the global counter with a per-client-ID sliding window (Redis or in-memory Map). Add rate limit tiers to the client configuration and return Retry-After headers on 429 responses.",
            related_issues=[],
        ),
        "priority": 55,
    },
    30: {
        "report": InvestigationReport(
            relevant_files=["src/modules/reporting/controller/report.controller.ts", "docs/api/"],
            git_history=["17217fe — Marcus Johnson — Dec 20 2025 — Add reporting module with CSV export"],
            root_cause="Documentation gap — the reporting module endpoints (/api/reports/*) are implemented but have no OpenAPI annotations or external documentation. Partners cannot discover or integrate with the reporting API.",
            complexity="low",
            fix_confidence=90,
            classification=InvestigationClassification.AUTO_FIX,
            summary="Reporting endpoints are undocumented. Add OpenAPI decorators and generate API docs.",
            recommended_fix="Add @ApiOperation and @ApiResponse decorators to all report controller methods. Generate OpenAPI spec and publish to the developer portal.",
            related_issues=[],
        ),
        "priority": 35,
    },
    31: {
        "report": InvestigationReport(
            relevant_files=["src/modules/accounts/controller/account.controller.ts", "src/modules/payments/controller/payment.controller.ts", "src/modules/transactions/controller/transaction.controller.ts"],
            git_history=["Multiple commits across controllers — validation logic is duplicated"],
            root_cause="Refactoring opportunity — input validation for request body fields (amount, currency, dates) is copy-pasted across 3+ controllers. Changes to validation rules must be made in multiple places, leading to inconsistencies.",
            complexity="medium",
            fix_confidence=80,
            classification=InvestigationClassification.AUTO_FIX,
            summary="Validation logic is duplicated across controllers. Extract shared validators into a common module.",
            recommended_fix="Create src/shared/validators/ with reusable validation functions (validateAmount, validateCurrency, validateDateRange) and replace the inline validation in each controller.",
            related_issues=[],
        ),
        "priority": 30,
    },
    32: {
        "report": InvestigationReport(
            relevant_files=["src/main.ts", "src/config/database.ts"],
            git_history=["8a12bc3 — Priya Patel — Oct 10 2025 — Initial project setup with database config"],
            root_cause="The app attempts to connect to the database immediately on startup without checking whether DATABASE_URL is set. If the env var is missing, the connection string is undefined and the driver throws an unhandled TypeError that crashes the process.",
            complexity="low",
            fix_confidence=98,
            classification=InvestigationClassification.AUTO_FIX,
            summary="Missing DATABASE_URL env var causes unhandled crash on startup. Add validation and a clear error message.",
            recommended_fix="Add a startup check in src/config/database.ts that validates DATABASE_URL is set and throws a descriptive error before attempting the connection.",
            related_issues=[],
        ),
        "priority": 75,
    },
    33: {
        "report": InvestigationReport(
            relevant_files=["package.json", "package-lock.json", "src/shared/utils/"],
            git_history=["Multiple dependency additions across project lifetime"],
            root_cause="Security audit — several dependencies have known CVEs. bcrypt@5.0.1 has a high-severity vulnerability, and jsonwebtoken@8.x has a moderate signature bypass issue. A full npm audit shows 4 high and 2 moderate vulnerabilities.",
            complexity="medium",
            fix_confidence=65,
            classification=InvestigationClassification.NEEDS_REVIEW,
            summary="Dependency audit found 6 vulnerabilities (4 high, 2 moderate). Upgrades need compatibility testing.",
            recommended_fix="Run npm audit fix for auto-fixable issues. Manually upgrade bcrypt to v6 and jsonwebtoken to v9. Test auth flows after upgrade since both are security-critical.",
            related_issues=[],
        ),
        "priority": 85,
    },
}


async def _seed_demo_investigations() -> int:
    """Fetch existing GitHub issues and seed them as completed investigations.

    Picks 5 random issues from _SEED_INVESTIGATIONS, fetches them from the
    GitHub API, and adds them to the dashboard as INVESTIGATION_COMPLETE with
    all telemetry steps marked completed and full investigation reports.
    No new issues are created — these are real, existing issues.
    """
    import random
    from app.services.playbook_router import playbook_router
    from app.services.github_service import github_service

    selected_numbers = random.sample(list(_SEED_INVESTIGATIONS.keys()), min(5, len(_SEED_INVESTIGATIONS)))
    seeded = 0

    for issue_number in selected_numbers:
        gh_issue = await github_service.get_issue(issue_number)
        if not gh_issue:
            logger.warning("Failed to fetch GitHub issue #%d for seeding", issue_number)
            continue

        issue_title = gh_issue.get("title", "")
        issue_body = gh_issue.get("body", "") or ""
        issue_url = gh_issue.get("html_url", "")
        issue_labels = [l["name"] if isinstance(l, dict) else l for l in gh_issue.get("labels", [])]

        inv = await investigation_store.create_investigation(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            issue_url=issue_url,
            issue_labels=issue_labels,
        )

        seed_data = _SEED_INVESTIGATIONS[issue_number]
        report: InvestigationReport = seed_data["report"]
        priority: int = seed_data.get("priority", 50)

        # Resolve playbook for the badge
        _issue_type, _playbook_id, _playbook_name = playbook_router.resolve_playbook(
            issue_title, issue_labels
        )

        # Mark all investigation telemetry steps as completed
        for step in inv.telemetry:
            step.status = "completed"
            step.timestamp = time.time()

        now = time.time()
        await investigation_store.update_investigation(
            inv.id,
            status=InvestigationStatus.INVESTIGATION_COMPLETE,
            playbook_name=_playbook_name,
            playbook_id=_playbook_id,
            investigation_report=report,
            classification=report.classification,
            started_at=now - random.uniform(30, 120),  # simulate elapsed time
            completed_at=now,
            priority=priority,
        )
        seeded += 1

    return seeded


def _get_simulation_data(investigation) -> dict | None:
    """Return pre-built simulation data matching known issues."""
    from app.models.investigation import InvestigationReport, InvestigationClassification

    title_lower = investigation.issue_title.lower()

    # Map known issues to realistic investigation results
    simulations: dict[str, dict] = {
        "currency formatting": {
            "report": InvestigationReport(
                relevant_files=["src/shared/utils/currency.ts", "src/modules/accounts/controller/account.controller.ts", "src/modules/payments/controller/payment.controller.ts"],
                git_history=["91c7038 — Sarah Chen — Oct 13 2025 — Add shared types, currency utils, date helpers"],
                root_cause="The formatCurrency function in src/shared/utils/currency.ts hardcodes 'en-US' as the locale parameter to Intl.NumberFormat. This means all currencies display with US formatting conventions ($1,234.56) regardless of the actual currency.",
                complexity="low",
                fix_confidence=95,
                classification=InvestigationClassification.AUTO_FIX,
                summary="Currency formatter hardcodes en-US locale. Simple fix: accept locale parameter or use currency-to-locale lookup.",
                recommended_fix="Add a currency-to-locale mapping and accept an optional locale parameter in formatCurrency(). Update all call sites to pass the account's locale or use the default mapping.",
                related_issues=[],
            ),
        },
        "pagination": {
            "report": InvestigationReport(
                relevant_files=["src/modules/transactions/controller/transaction.controller.ts", "src/modules/transactions/repository/transaction.repository.ts"],
                git_history=["97e21d6 — Marcus Johnson — Nov 18 2025 — Implement transactions module with pagination"],
                root_cause="Off-by-one in hasMore check: uses `page <= totalPages` instead of `page < totalPages`. When page equals totalPages, there are no more pages, but hasMore returns true.",
                complexity="low",
                fix_confidence=98,
                classification=InvestigationClassification.AUTO_FIX,
                summary="Pagination off-by-one: hasMore uses <= instead of <, causing infinite scroll loops on the last page.",
                recommended_fix="Change `hasMore: page <= result.totalPages` to `hasMore: page < result.totalPages` in transaction.controller.ts.",
                related_issues=[],
            ),
        },
        "jwt": {
            "report": InvestigationReport(
                relevant_files=["src/modules/auth/service/auth.service.ts"],
                git_history=["f549345 — Sarah Chen — Oct 18 2025 — Implement auth module with JWT token management"],
                root_cause="In AuthService.refreshAccessToken(), the old refresh token is never deleted from the refreshTokens set after being used. The comment even notes 'This line is missing' next to the commented-out delete call.",
                complexity="low",
                fix_confidence=97,
                classification=InvestigationClassification.AUTO_FIX,
                summary="JWT refresh token reuse vulnerability: old tokens are never invalidated, allowing replay attacks.",
                recommended_fix="Add `refreshTokens.delete(refreshToken)` before generating the new token pair in the refreshAccessToken method.",
                related_issues=[],
            ),
        },
        "monthly report": {
            "report": InvestigationReport(
                relevant_files=["src/modules/reporting/service/report.service.ts"],
                git_history=["17217fe — Marcus Johnson — Dec 20 2025 — Add reporting module with CSV export"],
                root_cause="The monthly report end date is hardcoded to day 27 instead of using the actual last day of the month. Line: `const endDate = new Date(year, month - 1, 27, 23, 59, 59)`. This was likely a copy-paste error from a test fixture.",
                complexity="low",
                fix_confidence=96,
                classification=InvestigationClassification.AUTO_FIX,
                summary="Monthly report misses transactions after the 27th due to hardcoded end date.",
                recommended_fix="Replace `new Date(year, month - 1, 27, 23, 59, 59)` with `new Date(year, month, 0, 23, 59, 59)` to get the actual last day of the month.",
                related_issues=[],
            ),
        },
        "fee calculation": {
            "report": InvestigationReport(
                relevant_files=["src/modules/payments/service/payment.service.ts"],
                git_history=["12cbaaa — Priya Patel — Nov 8 2025 — Add payment processing with fee calculation"],
                root_cause="Payment fees use floating-point arithmetic on dollar amounts. JavaScript floating point causes rounding errors (0.1 + 0.2 === 0.30000000000000004). The calculateFees, splitPayment, and calculateRunningBalance methods all operate on floats instead of integer cents.",
                complexity="medium",
                fix_confidence=82,
                classification=InvestigationClassification.AUTO_FIX,
                summary="Floating-point arithmetic on monetary amounts causes fee calculation rounding errors at scale.",
                recommended_fix="Convert all monetary calculations to use integer cents. Multiply by 100 at input boundaries, perform all arithmetic in cents, divide by 100 only for display.",
                related_issues=[9],
            ),
        },
        "csv export": {
            "report": InvestigationReport(
                relevant_files=["src/modules/reporting/service/report.service.ts"],
                git_history=["17217fe — Marcus Johnson — Dec 20 2025 — Add reporting module with CSV export"],
                root_cause="CSV export inserts transaction descriptions directly into cells without sanitization. If a description starts with =, +, -, or @, spreadsheet applications interpret it as a formula, enabling CSV formula injection attacks.",
                complexity="low",
                fix_confidence=90,
                classification=InvestigationClassification.AUTO_FIX,
                summary="CSV export is vulnerable to formula injection. Descriptions need to be sanitized before writing to cells.",
                recommended_fix="Prefix any cell value starting with =, +, -, @, tab, or carriage return with a single quote character to prevent formula interpretation.",
                related_issues=[],
            ),
        },
        "error monitoring": {
            "report": InvestigationReport(
                relevant_files=["src/shared/middleware/error-handler.ts"],
                git_history=["b24dc2a — Sarah Chen — Oct 20 2025 — Add auth middleware, error handler, and rate limiter"],
                root_cause="The global error handler treats all TypeError and ReferenceError instances as non-critical warnings. However, these error types can indicate real bugs in business logic (e.g., accessing properties of undefined). They should be logged as errors, not warnings.",
                complexity="medium",
                fix_confidence=72,
                classification=InvestigationClassification.NEEDS_REVIEW,
                summary="Error handler swallows TypeErrors as warnings, masking real production bugs in monitoring. Needs careful categorization strategy.",
                recommended_fix="Remove the TypeError/ReferenceError special case, or add context-aware categorization that distinguishes between client-input errors and internal bugs.",
                related_issues=[],
            ),
        },
        "timezone": {
            "report": InvestigationReport(
                relevant_files=["src/modules/transactions/repository/transaction.repository.ts", "src/shared/utils/dates.ts"],
                git_history=["91c7038 — Sarah Chen — Oct 13 2025 — Add shared types, currency utils, date helpers", "97e21d6 — Marcus Johnson — Nov 18 2025 — Implement transactions module"],
                root_cause="Date range filtering in the transaction repository compares timestamps directly without timezone normalization. The date utilities in dates.ts also use naive 24h arithmetic that breaks around DST transitions.",
                complexity="medium",
                fix_confidence=65,
                classification=InvestigationClassification.NEEDS_REVIEW,
                summary="Multiple timezone-related issues across date utilities and transaction queries. Needs a consistent timezone strategy.",
                recommended_fix="Adopt date-fns-tz for timezone-aware operations. Normalize all query date ranges to UTC before comparison. Fix daysAgo() to use calendar-day arithmetic instead of 24h multiples.",
                related_issues=[19],
            ),
        },
        "payments broken": {
            "report": InvestigationReport(
                relevant_files=["src/modules/payments/service/payment.service.ts", "src/modules/accounts/repository/account.repository.ts"],
                git_history=["12cbaaa — Priya Patel — Nov 8 2025", "57134c9 — Alex Rivera — Nov 3 2025"],
                root_cause="Multiple issues affect payments: (1) floating-point arithmetic causes fee rounding errors, (2) race condition on concurrent balance updates can cause lost updates. Together these explain the intermittent 'wrong amounts' reports.",
                complexity="medium",
                fix_confidence=60,
                classification=InvestigationClassification.NEEDS_REVIEW,
                summary="Payment issues are caused by a combination of floating-point arithmetic errors and race conditions on balance updates.",
                recommended_fix="Address floating-point money (#5) and race condition (#10) as prerequisite fixes.",
                related_issues=[5, 10],
            ),
        },
        "balances don't update": {
            "report": InvestigationReport(
                relevant_files=["src/modules/accounts/repository/account.repository.ts"],
                git_history=["57134c9 — Alex Rivera — Nov 3 2025 — Implement accounts module with balance operations"],
                root_cause="TOCTOU race condition in updateBalance(): reads current balance, waits (async), then writes back. Two concurrent updates both read the same balance, so one is lost.",
                complexity="high",
                fix_confidence=45,
                classification=InvestigationClassification.ESCALATE,
                summary="Race condition in balance updates causes lost transactions under concurrency. Requires database-level locking strategy — architectural decision needed.",
                recommended_fix="Requires migration to a real database with transactions and row-level locking (SELECT ... FOR UPDATE). This is an architectural change.",
                related_issues=[17],
            ),
        },
        "emails look": {
            "report": InvestigationReport(
                relevant_files=["src/modules/notifications/service/notification.service.ts", "src/shared/utils/validators.ts"],
                git_history=["f2d25bd — Alex Rivera — Dec 5 2025 — Add notification system with email templates"],
                root_cause="Email templates render user-provided variables (names, notes) via simple string replacement without HTML sanitization. Special characters in user names get rendered as raw HTML, causing display issues and a stored XSS vulnerability.",
                complexity="low",
                fix_confidence=88,
                classification=InvestigationClassification.AUTO_FIX,
                summary="Email templates don't sanitize user input, causing display issues and XSS vulnerability. sanitizeString() exists but isn't used.",
                recommended_fix="Use the existing sanitizeString() from validators.ts to sanitize all user-provided template variables before rendering.",
                related_issues=[18],
            ),
        },
        "legacy api": {
            "report": InvestigationReport(
                relevant_files=["src/legacy/bridge.js"],
                git_history=["9987d2b — Priya Patel — Jan 10 2026 — Add legacy API bridge for v1 compatibility"],
                root_cause="The legacy API bridge makes HTTP requests without any timeout configuration. If the legacy API is slow or unresponsive, requests hang indefinitely, eventually exhausting the connection pool.",
                complexity="low",
                fix_confidence=92,
                classification=InvestigationClassification.AUTO_FIX,
                summary="Legacy bridge has no request timeout, causing hangs when the legacy API is slow.",
                recommended_fix="Add a timeout option to the http/https request options in legacyRequest(). A 30-second timeout is reasonable.",
                related_issues=[],
            ),
        },
        "/api/users": {
            "report": InvestigationReport(
                relevant_files=[],
                git_history=[],
                root_cause="The /api/users endpoint does not exist in the current codebase. There is no users module — user management is handled through the auth module. This endpoint was likely removed during the v2 refactor.",
                complexity="low",
                fix_confidence=0,
                classification=InvestigationClassification.ESCALATE,
                summary="STALE ISSUE: The /api/users endpoint doesn't exist and never did in v2. This issue references removed/non-existent code. Recommend closing.",
                recommended_fix="Close this issue as stale. The admin dashboard should use the auth module endpoints instead.",
                related_issues=[],
            ),
        },
        "graphql": {
            "report": InvestigationReport(
                relevant_files=[],
                git_history=[],
                root_cause="This is a feature request, not a bug. Adding GraphQL would be a significant architectural addition requiring schema design, resolver implementation, and client updates.",
                complexity="high",
                fix_confidence=0,
                classification=InvestigationClassification.ESCALATE,
                summary="FEATURE REQUEST: GraphQL layer. Not a bug — requires architectural decision and dedicated sprint planning.",
                recommended_fix="This needs a tech design doc and team discussion. Not suitable for automated fixing.",
                related_issues=[],
            ),
        },
        "billing/invoice": {
            "report": InvestigationReport(
                relevant_files=[],
                git_history=[],
                root_cause="The file src/modules/billing/invoice.service.ts does not exist in the codebase. There is no billing module. This issue references non-existent code — likely from an abandoned branch or a different project.",
                complexity="low",
                fix_confidence=0,
                classification=InvestigationClassification.ESCALATE,
                summary="STALE ISSUE: References non-existent billing module. The file and directory don't exist in the codebase. Recommend closing.",
                recommended_fix="Close this issue. The referenced code doesn't exist.",
                related_issues=[],
            ),
        },
        "commonjs to esm": {
            "report": InvestigationReport(
                relevant_files=["src/legacy/bridge.js", "src/legacy/migration-utils.js", "tsconfig.json"],
                git_history=[],
                root_cause="This is a feature request / tech debt initiative. The legacy module uses CommonJS but the rest of the codebase uses TypeScript with module: commonjs in tsconfig. Migration to ESM would require touching every file.",
                complexity="high",
                fix_confidence=0,
                classification=InvestigationClassification.ESCALATE,
                summary="FEATURE REQUEST: ESM migration. Large-scale refactor requiring dedicated sprint. Not auto-fixable.",
                recommended_fix="Needs sprint planning. Consider as part of the legacy module deprecation in Q3 2026.",
                related_issues=[],
            ),
        },
        "race condition": {
            "report": InvestigationReport(
                relevant_files=["src/modules/accounts/repository/account.repository.ts", "src/modules/accounts/service/account.service.ts"],
                git_history=["57134c9 — Alex Rivera — Nov 3 2025 — Implement accounts module with balance operations"],
                root_cause="TOCTOU race condition: updateBalance() reads balance, does async work, writes back. Concurrent updates can read the same value and one write is lost. The code even has a comment documenting this.",
                complexity="high",
                fix_confidence=40,
                classification=InvestigationClassification.ESCALATE,
                summary="Race condition in balance updates is a critical financial integrity issue. Requires architectural decision on locking strategy (pessimistic vs optimistic vs event sourcing).",
                recommended_fix="Migrate to a database with proper transaction support and use SELECT ... FOR UPDATE or atomic UPDATE queries. This is an architectural decision.",
                related_issues=[10],
            ),
        },
        "html sanitization": {
            "report": InvestigationReport(
                relevant_files=["src/modules/notifications/service/notification.service.ts", "src/shared/utils/validators.ts"],
                git_history=["f2d25bd — Alex Rivera — Dec 5 2025"],
                root_cause="NotificationService.renderTemplate() does simple string replacement without sanitizing user-controlled values. The sanitizeString() utility exists but is never called in the notification service.",
                complexity="medium",
                fix_confidence=70,
                classification=InvestigationClassification.NEEDS_REVIEW,
                summary="XSS in email templates. sanitizeString() exists but isn't used. Decision needed on input vs output sanitization strategy.",
                recommended_fix="Apply sanitizeString() to all template variables at render time. Consider a more comprehensive approach for email-specific sanitization.",
                related_issues=[11],
            ),
        },
        "date/timezone": {
            "report": InvestigationReport(
                relevant_files=["src/shared/utils/dates.ts", "src/modules/transactions/repository/transaction.repository.ts", "src/modules/reporting/service/report.service.ts"],
                git_history=["91c7038 — Sarah Chen — Oct 13 2025", "97e21d6 — Marcus Johnson — Nov 18 2025", "17217fe — Marcus Johnson — Dec 20 2025"],
                root_cause="Multiple date-handling bugs stem from lack of timezone strategy: daysAgo() uses naive 24h arithmetic, isSameCalendarDay doesn't handle timezone offsets, date range queries compare timestamps without normalization.",
                complexity="high",
                fix_confidence=35,
                classification=InvestigationClassification.ESCALATE,
                summary="Cross-cutting date/timezone issues need a comprehensive strategy before individual fixes. Requires team discussion and library decision.",
                recommended_fix="Establish UTC storage standard, adopt date-fns-tz, audit all date utilities. Needs design doc.",
                related_issues=[4, 8],
            ),
        },
    }

    for key, sim in simulations.items():
        if key in title_lower:
            return sim

    return None


def _default_simulation(investigation) -> dict:
    """Default simulation for unknown issues."""
    from app.models.investigation import InvestigationReport, InvestigationClassification
    import random

    confidence = random.randint(30, 90)
    if confidence >= 80:
        classification = InvestigationClassification.AUTO_FIX
    elif confidence >= 50:
        classification = InvestigationClassification.NEEDS_REVIEW
    else:
        classification = InvestigationClassification.ESCALATE

    return {
        "report": InvestigationReport(
            relevant_files=["src/shared/utils/index.ts"],
            git_history=[],
            root_cause=f"Investigation of '{investigation.issue_title}' — automated analysis complete.",
            complexity="medium",
            fix_confidence=confidence,
            classification=classification,
            summary=f"Analysis of issue #{investigation.issue_number}: {investigation.issue_title}",
            recommended_fix="Further manual investigation recommended.",
            related_issues=[],
        ),
    }
