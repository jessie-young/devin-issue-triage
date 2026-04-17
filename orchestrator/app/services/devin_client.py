"""Devin API client for creating and polling sessions."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

INVESTIGATION_PROMPT_TEMPLATE = """You are investigating a GitHub issue in the repository {repo}.

## Issue Type: {issue_type}

## GitHub Issue #{issue_number}: {issue_title}

{issue_body}

---

## Investigation Protocol

Follow this structured investigation process and report findings at each step:

### Step 1: Codebase Scan
Search the codebase for files related to this issue. Look at relevant modules, services, controllers, and utilities.

### Step 2: Identify Relevant Files
List the specific files that are relevant to this issue. Include file paths.

### Step 3: Git History
Run `git log` and `git blame` on the relevant files. Identify which commits introduced the relevant code, who authored them, and when.

### Step 4: Root Cause / Feasibility Analysis
For bugs: determine the root cause — be specific about the exact line(s) of code and the mechanism.
For features: assess feasibility, identify which files/modules would need changes, and estimate scope.
For docs/refactoring: identify what needs updating and the scope of changes.

### Step 5: Complexity Assessment
Rate the complexity: low / medium / high. Consider:
- How many files need to change?
- Could the changes introduce regressions?
- Does it require architectural decisions?

### Step 6: Fix Confidence Score
Rate your confidence in being able to resolve this autonomously: 1-100
- 90-100: Simple, clear path with no ambiguity
- 70-89: Straightforward, minor decisions needed
- 50-69: Possible but involves trade-offs
- Below 50: Needs human input on approach

### Step 7: Classification
Based on your analysis, classify this investigation:
- **AUTO_FIX**: Confidence >= 80, low/medium complexity, clear path. You can resolve this autonomously.
- **NEEDS_REVIEW**: Confidence 50-79, or medium complexity with trade-offs. Human should review before proceeding.
- **ESCALATE**: Confidence < 50, high complexity, or requires architectural decisions. Needs senior engineer decision.

### Step 8: Related Issues
Check if other open issues might be related.

---

## Output Format

Please structure your final output as a report with these sections:
```
INVESTIGATION REPORT
====================
ISSUE TYPE: {issue_type}
RELEVANT FILES: [list file paths]
GIT HISTORY: [list relevant commits with authors and dates]
ROOT CAUSE: [detailed explanation]
COMPLEXITY: [low/medium/high]
FIX CONFIDENCE: [1-100]
CLASSIFICATION: [AUTO_FIX/NEEDS_REVIEW/ESCALATE]
RELATED ISSUES: [list issue numbers or "none"]
SUMMARY: [2-3 sentence summary]
RECOMMENDED FIX: [description of how to resolve]
```
"""

FIX_PROMPT_TEMPLATE = """You are resolving a GitHub issue in the repository {repo}.

## GitHub Issue #{issue_number}: {issue_title}

{issue_body}

## Investigation Summary

{investigation_summary}

## Root Cause

{root_cause}

## Recommended Fix

{recommended_fix}

---

## Fix Protocol

1. **Implement the fix**: Make the code changes described in the recommended fix. Follow existing code patterns and conventions.
2. **Write tests**: Add tests that verify the fix works and would have caught the original issue.
3. **Run the test suite**: Execute the project's test command and ensure all tests pass (both new and existing).
4. **Open a PR**: Create a pull request with a clear description referencing the issue number.

## Code Standards
- Follow existing patterns in neighboring files
- Keep changes minimal and focused
- Write tests for your changes
- Do not introduce new dependencies without justification
"""


class DevinClient:
    """Client for the Devin API v3 (Service User auth)."""

    def __init__(self) -> None:
        self._base_url = settings.devin_api_base_url
        self._api_key = settings.devin_api_key
        self._org_id = settings.devin_org_id

    @property
    def is_configured(self) -> bool:
        """Check if the client has valid credentials."""
        return bool(self._api_key and self._org_id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _org_url(self, path: str) -> str:
        """Build organization-scoped API URL."""
        return f"{self._base_url}/organizations/{self._org_id}{path}"

    async def _create_session_with_retry(
        self, payload: dict, max_retries: int = 3,
    ) -> dict:
        """Create a session with exponential backoff on 429 rate limits."""
        for attempt in range(max_retries + 1):
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self._org_url("/sessions"),
                    headers=self._headers(),
                    json=payload,
                )
                if resp.status_code == 429 and attempt < max_retries:
                    wait = 2 ** attempt * 5  # 5s, 10s, 20s
                    logger.warning(
                        "Devin API 429 rate limited (attempt %d/%d), retrying in %ds",
                        attempt + 1, max_retries + 1, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
        # Should not reach here, but just in case
        raise httpx.HTTPStatusError(
            "Max retries exceeded for 429", request=resp.request, response=resp  # type: ignore[possibly-undefined]
        )

    async def create_investigation_session(
        self,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        repo: str,
        playbook_id: str | None = None,
        issue_type: str = "bug",
    ) -> dict:
        """Create a Devin session to investigate a GitHub issue."""
        prompt = INVESTIGATION_PROMPT_TEMPLATE.format(
            repo=repo,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            issue_type=issue_type,
        )

        payload: dict = {"prompt": prompt}
        if playbook_id:
            payload["playbook_id"] = playbook_id

        return await self._create_session_with_retry(payload)

    async def create_fix_session(
        self,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        repo: str,
        investigation_summary: str,
        root_cause: str,
        recommended_fix: str,
        playbook_id: str | None = None,
    ) -> dict:
        """Create a Devin session to fix a bug."""
        prompt = FIX_PROMPT_TEMPLATE.format(
            repo=repo,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            investigation_summary=investigation_summary,
            root_cause=root_cause,
            recommended_fix=recommended_fix,
        )

        payload: dict = {"prompt": prompt}
        if playbook_id:
            payload["playbook_id"] = playbook_id

        return await self._create_session_with_retry(payload)

    async def stop_session(self, session_id: str) -> bool:
        """Stop a running/suspended Devin session. Returns True if stopped."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self._org_url(f"/sessions/{session_id}/stop"),
                    headers=self._headers(),
                )
                if resp.status_code in (200, 204):
                    return True
                logger.warning("Failed to stop session %s: %s", session_id, resp.status_code)
                return False
        except Exception as e:
            logger.warning("Error stopping session %s: %s", session_id, e)
            return False

    async def stop_all_running_sessions(self) -> int:
        """Stop all running/suspended sessions to free capacity. Returns count stopped."""
        sessions = await self.list_sessions(limit=100)
        stopped = 0
        for s in sessions:
            sid = s.get("session_id", "")
            status = s.get("status", "")
            if status in ("running", "suspended") and sid:
                # Don't stop this current Devin session (the orchestrator itself)
                if await self.stop_session(sid):
                    stopped += 1
        logger.info("Stopped %d old Devin sessions", stopped)
        return stopped

    async def get_session(self, session_id: str) -> dict:
        """Get session details including status."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                self._org_url(f"/sessions/{session_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_session_messages(self, session_id: str) -> list[dict]:
        """Get messages/output from a Devin session.

        The v3 API returns ``{"items": [...], "end_cursor": ..., ...}``.
        We normalise each item so downstream code can use ``msg["content"]``
        or ``msg["message"]`` interchangeably.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                self._org_url(f"/sessions/{session_id}/messages"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            # v3 wraps messages in {"items": [...]}
            if isinstance(data, dict):
                items = data.get("items", data.get("messages", []))
            else:
                items = data
            # Normalise: v3 uses "message" key; poller expects "content" too
            for item in items:
                if "content" not in item and "message" in item:
                    item["content"] = item["message"]
                if "id" not in item and "event_id" in item:
                    item["id"] = item["event_id"]
            return items

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """List recent Devin sessions."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                self._org_url("/sessions"),
                headers=self._headers(),
                params={"limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("sessions", [])


# Singleton
devin_client = DevinClient()
