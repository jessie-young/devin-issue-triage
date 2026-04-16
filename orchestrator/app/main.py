"""Devin Issue Triage Orchestrator — FastAPI application."""

import asyncio
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.investigations import router as investigations_router
from app.routers.webhooks import router as webhooks_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def _auto_seed():
    """Auto-seed investigations from GitHub issues on startup.

    In production mode (DEVIN_API_KEY set), only ingests issues into the queue
    without simulating them — real Devin sessions will handle investigation.
    In demo mode, simulates the full investigation pipeline with fake data.
    """
    from app.config import settings
    from app.services.github_service import github_service
    from app.services.investigation_store import investigation_store

    if not settings.github_token:
        logger.info("No GITHUB_TOKEN set, skipping auto-seed")
        return

    production_mode = bool(settings.devin_api_key)
    if production_mode:
        logger.info("Production mode detected (DEVIN_API_KEY set) — skipping auto-seed simulation")
        return

    try:
        from app.routers.investigations import simulate_investigation

        issues = await github_service.list_issues(state="open", per_page=30)
        created = 0
        for issue in issues:
            if "pull_request" in issue:
                continue
            inv = await investigation_store.create_investigation(
                issue_number=issue["number"],
                issue_title=issue.get("title") or "",
                issue_body=issue.get("body") or "",
                issue_url=issue.get("html_url") or "",
                issue_labels=[l.get("name", "") for l in issue.get("labels") or []],
            )
            created += 1

        logger.info(f"Auto-seed: ingested {created} issues")

        # Simulate investigations for all issues (skip GitHub comment posting on startup)
        all_investigations = investigation_store.get_all_investigations()
        simulated = 0
        for inv in all_investigations:
            try:
                await simulate_investigation(inv.id, post_comment=False)
                simulated += 1
            except Exception as e:
                logger.warning(f"Auto-seed: failed to simulate {inv.id}: {e}")
            await asyncio.sleep(0.05)

        logger.info(f"Auto-seed: simulated {simulated}/{created} investigations")

        # Route NEEDS_REVIEW/ESCALATE investigations to Completed column for demo
        from app.models.investigation import InvestigationClassification, InvestigationStatus
        routed = 0
        for inv in investigation_store.get_all_investigations():
            if inv.classification in (InvestigationClassification.NEEDS_REVIEW, InvestigationClassification.ESCALATE):
                await investigation_store.update_investigation(inv.id, status=InvestigationStatus.ROUTED)
                routed += 1
        logger.info(f"Auto-seed: routed {routed} NEEDS_REVIEW/ESCALATE investigations to completed")

    except Exception as e:
        logger.error(f"Auto-seed failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — loads playbooks and runs auto-seed on startup."""
    from app.services.playbook_router import playbook_router
    await playbook_router.load_playbooks()
    await _auto_seed()
    yield


app = FastAPI(title="Devin Issue Triage Orchestrator", lifespan=lifespan)

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(investigations_router)
app.include_router(webhooks_router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "devin-issue-triage-orchestrator"}
