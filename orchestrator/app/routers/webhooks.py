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
    issue_title = issue.get("title", "")
    issue_body = issue.get("body", "")
    issue_url = issue.get("html_url", "")
    issue_labels = [l.get("name", "") for l in issue.get("labels", [])]

    if not issue_number:
        raise HTTPException(status_code=400, detail="Missing issue number")

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
        logger.warning(f"Devin API unavailable, falling back to simulated investigation: {e}")
        # Fall back to simulation
        import asyncio as _asyncio
        from app.routers.investigations import simulate_investigation as _sim_fn

        async def _simulate_webhook_investigation():
            try:
                await _asyncio.sleep(1)
                await _sim_fn(investigation.id)
            except Exception as exc:
                logger.error(f"Simulated investigation failed for {investigation.id}: {exc}")

        _asyncio.ensure_future(_simulate_webhook_investigation())
        return {"status": "accepted_simulated", "investigation_id": investigation.id}
