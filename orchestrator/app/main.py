"""Mission Control Orchestrator — FastAPI application."""

import asyncio
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.missions import router as missions_router
from app.routers.webhooks import router as webhooks_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def _auto_seed():
    """Auto-seed missions from GitHub issues on startup for demo purposes."""
    from app.config import settings
    from app.services.github_service import github_service
    from app.services.mission_store import mission_store
    from app.routers.missions import simulate_investigation

    if not settings.github_token:
        logger.info("No GITHUB_TOKEN set, skipping auto-seed")
        return

    try:
        issues = await github_service.list_issues(state="open", per_page=30)
        created = 0
        for issue in issues:
            if "pull_request" in issue:
                continue
            mission = await mission_store.create_mission(
                issue_number=issue["number"],
                issue_title=issue.get("title", ""),
                issue_body=issue.get("body", ""),
                issue_url=issue.get("html_url", ""),
                issue_labels=[l.get("name", "") for l in issue.get("labels", [])],
            )
            created += 1

        logger.info(f"Auto-seed: ingested {created} issues")

        # Simulate investigations for all missions
        all_missions = mission_store.get_all_missions()
        simulated = 0
        for m in all_missions:
            try:
                await simulate_investigation(m.id)
                simulated += 1
            except Exception as e:
                logger.warning(f"Auto-seed: failed to simulate {m.id}: {e}")
            await asyncio.sleep(0.05)

        logger.info(f"Auto-seed: simulated {simulated}/{created} missions")

        # Route ASSIST/COMMAND missions to Completed column for demo
        from app.models.mission import MissionClassification, MissionStatus
        routed = 0
        for m in mission_store.get_all_missions():
            if m.classification in (MissionClassification.ASSIST, MissionClassification.COMMAND):
                await mission_store.update_mission(m.id, status=MissionStatus.ROUTED)
                routed += 1
        logger.info(f"Auto-seed: routed {routed} ASSIST/COMMAND missions to completed")

    except Exception as e:
        logger.error(f"Auto-seed failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — runs auto-seed on startup."""
    await _auto_seed()
    yield


app = FastAPI(title="Mission Control Orchestrator", lifespan=lifespan)

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(missions_router)
app.include_router(webhooks_router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "mission-control-orchestrator"}
