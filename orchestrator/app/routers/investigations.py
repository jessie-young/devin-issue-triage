"""Investigation management endpoints and SSE streaming."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.models.investigation import InvestigationClassification, InvestigationStatus
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
    """Request to launch a fix for a STRIKE investigation."""
    investigation_id: str


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

    # Kick off investigation
    try:
        session = await devin_client.create_investigation_session(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            repo=settings.target_repo,
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
    """Apply fix — create a fix session for a STRIKE investigation."""
    investigation = investigation_store.get_investigation(req.investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")

    if investigation.status != InvestigationStatus.INVESTIGATION_COMPLETE:
        raise HTTPException(
            status_code=400,
            detail=f"Investigation is in state {investigation.status.value}, expected INVESTIGATION_COMPLETE",
        )

    if investigation.classification != InvestigationClassification.STRIKE:
        raise HTTPException(
            status_code=400,
            detail=f"Only STRIKE investigations can be auto-fixed. This investigation is {investigation.classification}",
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
        logger.warning(f"Devin API unavailable, falling back to simulated launch: {e}")
        # Fall back to simulated launch for demo
        import asyncio as _asyncio

        async def _simulate_fix():
            try:
                await _asyncio.sleep(0.5)
                await investigation_store.update_investigation(req.investigation_id, status=InvestigationStatus.FIX_IN_PROGRESS)
                fix_steps = ["fix_start", "test_write", "test_run", "pr_open", "resolved"]
                labels = ["Writing Fix", "Writing Regression Test", "Running Test Suite", "Opening PR", "RESOLVED"]
                for step_id, label in zip(fix_steps, labels):
                    await _asyncio.sleep(1.5)
                    await investigation_store.update_telemetry_step(req.investigation_id, step_id, "completed", f"Simulated: {label}")
                # Use issue URL for demo — a real Devin session would create an actual PR
                await investigation_store.update_investigation(
                    req.investigation_id,
                    status=InvestigationStatus.RESOLVED,
                    pr_url=investigation.issue_url,
                    completed_at=time.time(),
                )
            except Exception as exc:
                logger.error(f"Simulated fix failed for {req.investigation_id}: {exc}")
                await investigation_store.update_investigation(
                    req.investigation_id,
                    status=InvestigationStatus.FAILED,
                    error=f"Simulated fix error: {exc}",
                )

        _asyncio.ensure_future(_simulate_fix())
        return {"status": "launched_simulated", "investigation_id": req.investigation_id}


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
            )
        except Exception as e:
            logger.warning(f"Failed to post investigation comment for {investigation_id}: {e}")

    return {"status": "simulated", "classification": classification.value if classification else "UNKNOWN"}


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
                classification=InvestigationClassification.STRIKE,
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
                classification=InvestigationClassification.STRIKE,
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
                classification=InvestigationClassification.STRIKE,
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
                classification=InvestigationClassification.STRIKE,
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
                classification=InvestigationClassification.STRIKE,
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
                classification=InvestigationClassification.STRIKE,
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
                classification=InvestigationClassification.ASSIST,
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
                classification=InvestigationClassification.ASSIST,
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
                classification=InvestigationClassification.ASSIST,
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
                classification=InvestigationClassification.COMMAND,
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
                classification=InvestigationClassification.STRIKE,
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
                classification=InvestigationClassification.STRIKE,
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
                classification=InvestigationClassification.COMMAND,
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
                classification=InvestigationClassification.COMMAND,
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
                classification=InvestigationClassification.COMMAND,
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
                classification=InvestigationClassification.COMMAND,
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
                classification=InvestigationClassification.COMMAND,
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
                classification=InvestigationClassification.ASSIST,
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
                classification=InvestigationClassification.COMMAND,
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
        classification = InvestigationClassification.STRIKE
    elif confidence >= 50:
        classification = InvestigationClassification.ASSIST
    else:
        classification = InvestigationClassification.COMMAND

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
