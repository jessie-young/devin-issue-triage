"""GitHub API service for posting comments and reading issues."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings
from app.models.investigation import InvestigationReport, InvestigationClassification

logger = logging.getLogger(__name__)

COMMENT_TEMPLATE = """## Investigation Report

**Investigation ID:** {investigation_id}
**Classification:** {classification_badge}
**Fix Confidence:** {confidence}/100
**Complexity:** {complexity}

---

### Root Cause

{root_cause}

### Relevant Files

{files_list}

### Git History

{git_history}

### Related Issues

{related_issues}

### Recommended Fix

{recommended_fix}

---

{classification_note}

> _This investigation was performed automatically by [Devin Issue Triage](https://github.com/jessie-young/demo-finserv-repo) via Devin AI._
"""


def _classification_badge(classification: InvestigationClassification | None) -> str:
    if classification == InvestigationClassification.AUTO_FIX:
        return "Auto-fix — Fixable automatically"
    elif classification == InvestigationClassification.NEEDS_REVIEW:
        return "Needs Review — Human review needed"
    elif classification == InvestigationClassification.ESCALATE:
        return "Escalate — Senior decision required"
    return "UNKNOWN"


def _classification_note(classification: InvestigationClassification | None) -> str:
    if classification == InvestigationClassification.AUTO_FIX:
        return (
            "**Next step:** This issue has been classified as auto-fixable. "
            "Click **Apply Fix** on the Issue Triage dashboard to have Devin implement the fix and open a PR."
        )
    elif classification == InvestigationClassification.NEEDS_REVIEW:
        return (
            "**Next step:** This issue needs human review of the investigation findings before proceeding. "
            "Please review the root cause analysis and recommended fix, then decide whether to proceed with the automated fix."
        )
    elif classification == InvestigationClassification.ESCALATE:
        return (
            "**Next step:** This issue requires a senior engineering decision. "
            "The automated investigation has identified the problem but the fix involves architectural trade-offs "
            "that need human judgment."
        )
    return ""


class GitHubService:
    """Service for interacting with the GitHub API."""

    def __init__(self) -> None:
        self._token = settings.github_token
        self._repo = settings.target_repo

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

    async def post_investigation_comment(
        self,
        issue_number: int,
        investigation_id: str,
        report: InvestigationReport,
    ) -> dict | None:
        """Post the investigation report as a comment on the GitHub issue."""
        files_list = "\n".join(f"- `{f}`" for f in report.relevant_files) or "- _None identified_"
        git_history = "\n".join(f"- {h}" for h in report.git_history) or "- _No relevant history found_"
        related = ", ".join(f"#{i}" for i in report.related_issues) if report.related_issues else "None"

        body = COMMENT_TEMPLATE.format(
            investigation_id=investigation_id,
            classification_badge=_classification_badge(report.classification),
            confidence=report.fix_confidence,
            complexity=report.complexity,
            root_cause=report.root_cause or "_Not determined_",
            files_list=files_list,
            git_history=git_history,
            related_issues=related,
            recommended_fix=report.recommended_fix or "_No fix recommended yet_",
            classification_note=_classification_note(report.classification),
        )

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://api.github.com/repos/{self._repo}/issues/{issue_number}/comments",
                    headers=self._headers(),
                    json={"body": body},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Failed to post comment on issue #{issue_number}: {e}")
            return None

    async def get_issue(self, issue_number: int) -> dict | None:
        """Fetch a single GitHub issue."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{self._repo}/issues/{issue_number}",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch issue #{issue_number}: {e}")
            return None

    async def list_issues(self, state: str = "open", per_page: int = 30) -> list[dict]:
        """List issues on the target repo."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{self._repo}/issues",
                    headers=self._headers(),
                    params={"state": state, "per_page": per_page, "sort": "created", "direction": "asc"},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Failed to list issues: {e}")
            return []


# Singleton
github_service = GitHubService()
