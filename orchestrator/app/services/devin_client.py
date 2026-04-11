"""Devin API client for creating and polling sessions."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

INVESTIGATION_PROMPT_TEMPLATE = """You are investigating a bug report from the FinServ Platform repository ({repo}).

## GitHub Issue #{issue_number}: {issue_title}

{issue_body}

---

## Investigation Protocol

Follow this structured investigation process and report findings at each step:

### Step 1: Codebase Scan
Search the codebase for files related to this issue. Look at relevant modules, services, controllers, and utilities.

### Step 2: Identify Relevant Files
List the specific files that are relevant to this bug. Include file paths.

### Step 3: Git History
Run `git log` and `git blame` on the relevant files. Identify which commits introduced the problematic code, who authored them, and when.

### Step 4: Root Cause Analysis
Determine the root cause of the bug. Be specific about the exact line(s) of code causing the issue and explain the mechanism.

### Step 5: Complexity Assessment
Rate the complexity: low / medium / high. Consider:
- How many files need to change?
- Could the fix introduce regressions?
- Does it require architectural changes?

### Step 6: Fix Confidence Score
Rate your confidence in being able to fix this autonomously: 1-100
- 90-100: Simple, clear fix with no ambiguity
- 70-89: Straightforward fix, minor decisions needed
- 50-69: Fix is possible but involves trade-offs
- Below 50: Needs human input on approach

### Step 7: Classification
Based on your analysis, classify this mission:
- **STRIKE**: Fix confidence >= 80, low/medium complexity, clear fix path. You can fix this autonomously.
- **ASSIST**: Fix confidence 50-79, or medium complexity with trade-offs. Human should review your briefing before proceeding.
- **COMMAND**: Fix confidence < 50, high complexity, or requires architectural decisions. Needs senior engineer decision.

### Step 8: Related Issues
Check if other open issues might be related to the same root cause.

---

## Output Format

Please structure your final output as a report with these sections:
```
INVESTIGATION REPORT
====================
RELEVANT FILES: [list file paths]
GIT HISTORY: [list relevant commits with authors and dates]
ROOT CAUSE: [detailed explanation]
COMPLEXITY: [low/medium/high]
FIX CONFIDENCE: [1-100]
CLASSIFICATION: [STRIKE/ASSIST/COMMAND]
RELATED ISSUES: [list issue numbers or "none"]
SUMMARY: [2-3 sentence summary]
RECOMMENDED FIX: [description of how to fix]
```
"""

FIX_PROMPT_TEMPLATE = """You are fixing a bug in the FinServ Platform repository ({repo}).

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

1. **Write the fix**: Implement the code changes described in the recommended fix. Follow existing code patterns and conventions.
2. **Write a regression test**: Add a test in the appropriate `__tests__/` directory that would have caught this bug.
3. **Run the test suite**: Execute `npm test` and ensure all tests pass (both new and existing).
4. **Open a PR**: Create a pull request with a clear description referencing the issue number.

## Code Standards
- TypeScript strict mode
- Use integer cents for monetary amounts (not floating point dollars)
- Write regression tests in the module's `__tests__/` directory
- Follow existing patterns in neighboring files
- Keep changes minimal and focused
"""


class DevinClient:
    """Client for the Devin API."""

    def __init__(self) -> None:
        self._base_url = settings.devin_api_base_url
        self._token = settings.devin_api_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def create_investigation_session(
        self,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        repo: str,
        playbook_id: str | None = None,
    ) -> dict:
        """Create a Devin session to investigate a GitHub issue."""
        prompt = INVESTIGATION_PROMPT_TEMPLATE.format(
            repo=repo,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
        )

        payload: dict = {"prompt": prompt}
        if playbook_id:
            payload["playbook_id"] = playbook_id

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/sessions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

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

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/sessions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_session(self, session_id: str) -> dict:
        """Get session details including status."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._base_url}/sessions/{session_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_session_messages(self, session_id: str) -> list[dict]:
        """Get messages/output from a Devin session."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._base_url}/sessions/{session_id}/messages",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            # The API returns messages in a list
            return data if isinstance(data, list) else data.get("messages", [])

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """List recent Devin sessions."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._base_url}/sessions",
                headers=self._headers(),
                params={"limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("sessions", [])


# Singleton
devin_client = DevinClient()
