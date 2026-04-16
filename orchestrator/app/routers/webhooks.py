"""GitHub webhook receiver for issue events."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.models.investigation import InvestigationStatus
from app.services.devin_client import devin_client
from app.services.investigation_store import investigation_store
from app.services.playbook_router import playbook_router
from app.services.session_poller import session_poller

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    if not secret:
        return True  # Skip verification if no secret configured
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
):
    """Handle GitHub webhook events (issues opened/labeled)."""
    body = await request.body()

    # Verify signature if secret is configured
    if settings.github_webhook_secret:
        if not _verify_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "issues":
        return {"status": "ignored", "reason": f"event type '{x_github_event}' not handled"}

    payload = await request.json()
    action = payload.get("action")

    if action not in ("opened", "labeled"):
        return {"status": "ignored", "reason": f"action '{action}' not handled"}

    issue = payload.get("issue", {})
    issue_number = issue.get("number")
    issue_title = issue.get("title") or ""
    issue_body = issue.get("body") or ""
    issue_url = issue.get("html_url") or ""
    issue_labels = [l.get("name", "") for l in issue.get("labels") or []]

    if not issue_number:
        raise HTTPException(status_code=400, detail="Missing issue number")

    # Check if this issue already exists (e.g. seeded by Reset)
    existing = investigation_store.get_investigation(f"FINSERV-{issue_number}")
    if existing is not None:
        logger.info(
            "Issue #%s already exists as %s (status=%s) — skipping webhook processing",
            issue_number, existing.id, existing.status.value,
        )
        return {"status": "skipped", "reason": "investigation already exists", "investigation_id": existing.id}

    # Create investigation
    investigation = await investigation_store.create_investigation(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        issue_url=issue_url,
        issue_labels=issue_labels,
    )

    # Detect issue type and resolve playbook
    issue_type, playbook_id, playbook_name = playbook_router.resolve_playbook(issue_title, issue_labels)
    logger.info(
        "Issue #%s detected as '%s' → playbook '%s' (%s)",
        issue_number, issue_type.value, playbook_name or "(none)", playbook_id or "(none)",
    )

    # Store playbook info on the investigation
    await investigation_store.update_investigation(
        investigation.id,
        playbook_name=playbook_name,
        playbook_id=playbook_id,
    )

    # If auto-triage is OFF, leave in Queue
    if not investigation_store.auto_triage:
        logger.info("Auto-triage OFF — issue #%s queued without starting investigation", issue_number)
        return {"status": "queued", "investigation_id": investigation.id}

    # Auto-triage is ON — kick off investigation immediately
    try:
        from app.routers.investigations import _start_investigation
        session_id = await _start_investigation(investigation)
        return {"status": "accepted", "investigation_id": investigation.id, "session_id": session_id}

    except Exception as e:
        logger.error(f"Failed to start investigation for issue #{issue_number}: {e}")
        return {"status": "queued", "investigation_id": investigation.id, "error": str(e)}
