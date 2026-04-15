"""Dynamic playbook routing based on issue type detection.

Detects issue type from title prefixes and GitHub labels, then looks up
the appropriate Devin playbook by name (not hardcoded ID).
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class IssueType(str, Enum):
    """Detected issue type used for playbook routing."""
    BUG = "bug"
    FEATURE = "feature"
    DOCS = "docs"
    REFACTORING = "refactoring"
    SECURITY = "security"
    INVESTIGATION = "investigation"


# --- Issue type detection ---------------------------------------------------

# Title prefixes that signal issue type (case-insensitive, before the first colon)
_TITLE_PREFIX_MAP: dict[str, IssueType] = {
    "bug": IssueType.BUG,
    "fix": IssueType.BUG,
    "feature": IssueType.FEATURE,
    "feat": IssueType.FEATURE,
    "enhancement": IssueType.FEATURE,
    "docs": IssueType.DOCS,
    "documentation": IssueType.DOCS,
    "refactor": IssueType.REFACTORING,
    "refactoring": IssueType.REFACTORING,
    "security": IssueType.SECURITY,
    "investigation": IssueType.INVESTIGATION,
    "audit": IssueType.INVESTIGATION,
}

# GitHub label → issue type (labels take priority over title prefix)
_LABEL_MAP: dict[str, IssueType] = {
    "bug": IssueType.BUG,
    "enhancement": IssueType.FEATURE,
    "feature": IssueType.FEATURE,
    "feature-request": IssueType.FEATURE,
    "documentation": IssueType.DOCS,
    "docs": IssueType.DOCS,
    "refactoring": IssueType.REFACTORING,
    "refactor": IssueType.REFACTORING,
    "security": IssueType.SECURITY,
    "investigation": IssueType.INVESTIGATION,
}

# Issue type → playbook name (must match exactly what's in Devin)
_ISSUE_TYPE_TO_PLAYBOOK_NAME: dict[IssueType, str] = {
    IssueType.BUG: "Bug Investigation Protocol",
    IssueType.FEATURE: "Feature Request Evaluation Protocol",
    IssueType.DOCS: "Documentation & Refactoring Assessment Protocol",
    IssueType.REFACTORING: "Documentation & Refactoring Assessment Protocol",
    IssueType.SECURITY: "Bug Investigation Protocol",
    IssueType.INVESTIGATION: "Bug Investigation Protocol",
}


def detect_issue_type(title: str, labels: list[str]) -> IssueType:
    """Detect issue type from title prefix and/or GitHub labels.

    Labels take priority over title prefix. Falls back to BUG if
    no signal is found (bugs are the most common issue type).
    """
    # 1. Check labels first (higher confidence signal)
    for label in labels:
        normalized = label.lower().strip()
        if normalized in _LABEL_MAP:
            detected = _LABEL_MAP[normalized]
            logger.info("Issue type '%s' detected from label '%s'", detected.value, label)
            return detected

    # 2. Parse title prefix (text before first colon)
    prefix_match = re.match(r"^\s*([A-Za-z]+)\s*:", title)
    if prefix_match:
        prefix = prefix_match.group(1).lower()
        if prefix in _TITLE_PREFIX_MAP:
            detected = _TITLE_PREFIX_MAP[prefix]
            logger.info("Issue type '%s' detected from title prefix '%s'", detected.value, prefix)
            return detected

    # 3. Default to bug (most common)
    logger.info("No issue type signal found, defaulting to 'bug'")
    return IssueType.BUG


# --- Playbook lookup --------------------------------------------------------

class PlaybookRouter:
    """Looks up Devin playbook IDs by name at startup, then routes issues."""

    def __init__(self) -> None:
        # {playbook_title: playbook_id}
        self._index: dict[str, str] = {}
        self._loaded = False

    async def load_playbooks(self) -> None:
        """Fetch all playbooks from the Devin API and build the name→id index."""
        if not settings.devin_api_key or not settings.devin_org_id:
            logger.warning("Devin API not configured — playbook routing disabled")
            return

        try:
            url = f"{settings.devin_api_base_url}/organizations/{settings.devin_org_id}/playbooks"
            headers = {
                "Authorization": f"Bearer {settings.devin_api_key}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            playbooks = data if isinstance(data, list) else data.get("playbooks", [])
            self._index = {}
            for pb in playbooks:
                title = pb.get("title") or pb.get("name", "")
                pb_id = pb.get("playbook_id") or pb.get("id", "")
                if title and pb_id:
                    self._index[title] = pb_id

            self._loaded = True
            logger.info(
                "Loaded %d playbooks: %s",
                len(self._index),
                list(self._index.keys()),
            )
        except Exception:
            logger.exception("Failed to load playbooks from Devin API")

    def get_playbook_id(self, issue_type: IssueType) -> Optional[str]:
        """Return the playbook ID for the given issue type, or None."""
        if not self._loaded:
            return None
        playbook_name = _ISSUE_TYPE_TO_PLAYBOOK_NAME.get(issue_type)
        if not playbook_name:
            return None
        pb_id = self._index.get(playbook_name)
        if pb_id:
            logger.info(
                "Routing issue type '%s' → playbook '%s' (%s)",
                issue_type.value,
                playbook_name,
                pb_id,
            )
        else:
            logger.warning(
                "Playbook '%s' not found for issue type '%s'",
                playbook_name,
                issue_type.value,
            )
        return pb_id

    def resolve_playbook(self, title: str, labels: list[str]) -> tuple[IssueType, Optional[str]]:
        """Detect issue type and return (issue_type, playbook_id) in one call."""
        issue_type = detect_issue_type(title, labels)
        playbook_id = self.get_playbook_id(issue_type)
        return issue_type, playbook_id


# Singleton
playbook_router = PlaybookRouter()
