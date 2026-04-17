"""Background task that polls Devin sessions and emits telemetry events."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

from app.config import settings
from app.models.investigation import (
    InvestigationReport,
    Investigation,
    InvestigationClassification,
    InvestigationStatus,
    SSEEvent,
)
from app.services.devin_client import devin_client
from app.services.event_bus import event_bus
from app.services.github_service import github_service
from app.services.investigation_store import investigation_store

logger = logging.getLogger(__name__)

# Keywords that indicate investigation progress
TELEMETRY_KEYWORDS = {
    "scan": ["scanning", "searching", "grep", "find", "looking at", "examining", "reading"],
    "files": ["found file", "relevant file", "identified", "located", "src/"],
    "git": ["git log", "git blame", "commit", "authored by", "history"],
    "root_cause": ["root cause", "the issue is", "the bug is", "problem is", "because"],
    "classify": ["confidence", "classification", "AUTO_FIX", "NEEDS_REVIEW", "ESCALATE", "complexity"],
}

FIX_TELEMETRY_KEYWORDS = {
    "fix_start": ["implementing", "writing fix", "changing", "updating", "modifying"],
    "test_run": ["npm test", "running test", "test suite", "PASS", "FAIL", "jest", "test", "regression"],
    "pr_open": ["pull request", "PR", "opening pr", "created pr", "branch"],
    "resolved": ["complete", "done", "finished", "merged"],
}


def _clean_root_cause(text: str) -> str:
    """Clean up raw root cause text from Devin output for human-readable display.

    Strips internal file paths, <ref_snippet> tags, code fences, excessive
    technical detail, and truncates to a reasonable length.
    """
    # Remove <ref_snippet .../> and <ref_file .../> XML tags
    text = re.sub(r"<ref_snippet[^>]*/\s*>", "", text)
    text = re.sub(r"<ref_file[^>]*/\s*>", "", text)

    # Remove absolute file paths (e.g. /home/ubuntu/repos/...)
    text = re.sub(r"/home/ubuntu/[^\s)\"']+", "", text)

    # Remove code fences
    text = re.sub(r"```[\s\S]*?```", "", text)

    # Remove backtick-quoted shell commands (e.g. `grep -ri "swagger|..."`)
    text = re.sub(r"`[^`]{50,}`", "", text)

    # Collapse numbered lists into sentences (e.g. "1. Foo 2. Bar" → "Foo. Bar.")
    text = re.sub(r"\n\s*\d+\.\s*", ". ", text)

    # Strip leading prefixes like "/ FEASIBILITY:" or "/ ROOT CAUSE:"
    text = re.sub(r"^[/\s]*(?:FEASIBILITY|ROOT CAUSE)[:\s]*", "", text, flags=re.IGNORECASE)

    # Collapse multiple whitespace / newlines
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate to first 300 chars at a sentence boundary if possible
    max_len = 300
    if len(text) > max_len:
        # Try to cut at a sentence boundary
        cut = text[:max_len].rfind(". ")
        if cut > 100:
            text = text[:cut + 1]
        else:
            text = text[:max_len].rstrip() + "…"

    return text


def _parse_investigation_report(messages: list[dict]) -> Optional[InvestigationReport]:
    """Parse structured investigation output from Devin's messages."""
    # Filter out user prompt messages — they contain template keywords
    # (e.g. "COMPLEXITY: low / medium / high") that would cause incorrect
    # regex matches and override Devin's actual findings.
    full_text = "\n".join(
        m.get("content", "") or m.get("message", "") or ""
        for m in messages
        if isinstance(m, dict) and m.get("source") != "user"
    )

    if not full_text:
        return None

    report = InvestigationReport()

    # Extract relevant files
    file_pattern = r"(?:src/[a-zA-Z0-9_/\-\.]+\.(?:ts|js|json))"
    files = list(set(re.findall(file_pattern, full_text)))
    report.relevant_files = files[:20]

    # Extract root cause
    rc_match = re.search(r"ROOT CAUSE[:\s]*\n(.+?)(?=\n(?:COMPLEXITY|FIX CONFIDENCE|CLASSIFICATION|\Z))", full_text, re.DOTALL | re.IGNORECASE)
    if rc_match:
        report.root_cause = _clean_root_cause(rc_match.group(1).strip())
    else:
        # Fallback: look for "the bug is" or "the issue is"
        for pattern in [r"(?:root cause|the bug is|the issue is|the problem is)[:\s]+(.+?)(?:\n\n|\Z)", r"(?:because)[:\s]+(.+?)(?:\n\n|\Z)"]:
            m = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
            if m:
                report.root_cause = _clean_root_cause(m.group(1).strip())
                break

    # Extract complexity
    cx_match = re.search(r"COMPLEXITY[:\s]*(low|medium|high)", full_text, re.IGNORECASE)
    if cx_match:
        report.complexity = cx_match.group(1).lower()

    # Extract fix confidence
    fc_match = re.search(r"FIX CONFIDENCE[:\s]*(\d+)", full_text, re.IGNORECASE)
    if fc_match:
        report.fix_confidence = min(100, max(0, int(fc_match.group(1))))

    # Extract classification (with backward-compat mapping for old names)
    _CLASSIFICATION_ALIASES = {
        "STRIKE": "AUTO_FIX",
        "ASSIST": "NEEDS_REVIEW",
        "COMMAND": "ESCALATE",
    }
    cl_match = re.search(r"CLASSIFICATION[:\s]*(AUTO_FIX|NEEDS_REVIEW|ESCALATE|STRIKE|ASSIST|COMMAND)", full_text, re.IGNORECASE)
    if cl_match:
        classification_str = cl_match.group(1).upper()
        classification_str = _CLASSIFICATION_ALIASES.get(classification_str, classification_str)
        try:
            report.classification = InvestigationClassification(classification_str)
        except ValueError:
            pass

    # Extract summary
    sm_match = re.search(r"SUMMARY[:\s]*\n(.+?)(?=\n(?:RECOMMENDED FIX|\Z))", full_text, re.DOTALL | re.IGNORECASE)
    if sm_match:
        report.summary = sm_match.group(1).strip()[:500]

    # Extract recommended fix
    rf_match = re.search(r"RECOMMENDED FIX[:\s]*\n(.+?)(?=\n```|\Z)", full_text, re.DOTALL | re.IGNORECASE)
    if rf_match:
        report.recommended_fix = rf_match.group(1).strip()[:1000]

    # Extract related issues
    ri_match = re.search(r"RELATED ISSUES[:\s]*(.+?)(?=\n\n|\Z)", full_text, re.IGNORECASE)
    if ri_match:
        numbers = re.findall(r"#?(\d+)", ri_match.group(1))
        report.related_issues = [int(n) for n in numbers]

    # Auto-classify if not explicitly classified
    if not report.classification:
        if report.fix_confidence >= 80:
            report.classification = InvestigationClassification.AUTO_FIX
        elif report.fix_confidence >= 50:
            report.classification = InvestigationClassification.NEEDS_REVIEW
        else:
            report.classification = InvestigationClassification.ESCALATE

    return report


def _detect_telemetry_progress(
    message_text: str,
    keywords: dict[str, list[str]],
) -> list[str]:
    """Detect which telemetry steps are indicated by a message."""
    text_lower = message_text.lower()
    triggered = []
    for step_id, kws in keywords.items():
        if any(kw in text_lower for kw in kws):
            triggered.append(step_id)
    return triggered


class SessionPoller:
    """Polls active Devin sessions for progress updates."""

    def __init__(self) -> None:
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._seen_messages: dict[str, set[str]] = {}

    async def start_polling(self, investigation_id: str, session_id: str, phase: str = "investigation") -> None:
        """Start polling a session for an investigation."""
        task_key = f"{investigation_id}:{phase}"
        if task_key in self._active_tasks:
            return

        task = asyncio.create_task(
            self._poll_loop(investigation_id, session_id, phase)
        )
        self._active_tasks[task_key] = task

    def cancel_all(self) -> int:
        """Cancel all active polling tasks. Returns count cancelled."""
        count = 0
        for task_key, task in list(self._active_tasks.items()):
            if not task.done():
                task.cancel()
                count += 1
        self._active_tasks.clear()
        self._seen_messages.clear()
        logger.info("Cancelled %d active polling tasks", count)
        return count

    async def _poll_loop(self, investigation_id: str, session_id: str, phase: str) -> None:
        """Main polling loop for a session."""
        task_key = f"{investigation_id}:{phase}"
        self._seen_messages[task_key] = set()
        keywords = TELEMETRY_KEYWORDS if phase == "investigation" else FIX_TELEMETRY_KEYWORDS
        completed_steps: set[str] = set()

        try:
            start_time = time.time()
            while time.time() - start_time < settings.max_poll_duration_seconds:
                try:
                    # Check session status
                    session = await devin_client.get_session(session_id)
                    session_status = session.get("status", "")

                    # Get new messages
                    messages = await devin_client.get_session_messages(session_id)
                    new_messages = []
                    for msg in messages:
                        msg_id = msg.get("id", str(hash(str(msg))))
                        if msg_id not in self._seen_messages[task_key]:
                            self._seen_messages[task_key].add(msg_id)
                            new_messages.append(msg)

                    # Process new messages for telemetry
                    for msg in new_messages:
                        # Skip our own prompt messages — they contain all the
                        # telemetry keywords and would instantly mark every step
                        # as completed.  Only Devin's responses carry real progress.
                        if msg.get("source") == "user":
                            continue
                        text = msg.get("content", "") or msg.get("message", "") or ""
                        if not text:
                            continue

                        triggered_steps = _detect_telemetry_progress(text, keywords)
                        for step_id in triggered_steps:
                            if step_id not in completed_steps:
                                completed_steps.add(step_id)
                                await investigation_store.update_telemetry_step(
                                    investigation_id, step_id, "completed", text[:200]
                                )

                        # Emit raw telemetry event for the strip
                        preview = text[:150].replace("\n", " ")
                        await event_bus.publish(SSEEvent(
                            event_type="telemetry_raw",
                            investigation_id=investigation_id,
                            data={"text": preview},
                        ))

                    # Check if session is finished (or suspended — Devin
                    # sessions may be suspended when ACUs run out).
                    is_terminal = session_status in (
                        "finished", "stopped", "failed", "suspended",
                    )

                    # Also detect early completion: if Devin has already
                    # produced a full investigation report in its messages
                    # the session may stay "running" for a while before
                    # transitioning.  We can handle the report immediately.
                    report_ready = False
                    if not is_terminal and phase == "investigation":
                        full_text = "\n".join(
                            m.get("content", "") or m.get("message", "") or ""
                            for m in messages
                            if isinstance(m, dict) and m.get("source") != "user"
                        )
                        if "INVESTIGATION REPORT" in full_text and "CLASSIFICATION" in full_text:
                            report_ready = True
                            logger.info(
                                "Report detected in messages for %s while session still %s — completing early",
                                investigation_id, session_status,
                            )

                    if is_terminal or report_ready:
                        if phase == "investigation":
                            await self._handle_investigation_complete(
                                investigation_id, session_id, messages
                            )
                        elif phase == "fix":
                            await self._handle_fix_complete(
                                investigation_id, session_id, session, messages
                            )
                        break

                except Exception as e:
                    logger.error(f"Poll error for {investigation_id}: {e}")

                await asyncio.sleep(settings.poll_interval_seconds)

        finally:
            self._active_tasks.pop(task_key, None)
            self._seen_messages.pop(task_key, None)

    async def _handle_investigation_complete(
        self, investigation_id: str, session_id: str, messages: list[dict]
    ) -> None:
        """Handle completion of an investigation session."""
        report = _parse_investigation_report(messages)

        investigation = investigation_store.get_investigation(investigation_id)
        if not investigation:
            return

        if report:
            # Mark all telemetry steps as completed
            for step in investigation.telemetry:
                if step.status != "completed":
                    await investigation_store.update_telemetry_step(
                        investigation_id, step.id, "completed"
                    )

            await investigation_store.update_investigation(
                investigation_id,
                status=InvestigationStatus.INVESTIGATION_COMPLETE,
                investigation_report=report,
                classification=report.classification,
                completed_at=time.time(),
                elapsed_seconds=time.time() - (investigation.started_at or investigation.created_at),
            )

            # Post comment to GitHub (include playbook info)
            await github_service.post_investigation_comment(
                investigation.issue_number, investigation_id, report,
                playbook_name=investigation.playbook_name,
                playbook_id=investigation.playbook_id,
            )

            await event_bus.publish(SSEEvent(
                event_type="investigation_complete",
                investigation_id=investigation_id,
                data={
                    "classification": report.classification.value if report.classification else "UNKNOWN",
                    "confidence": report.fix_confidence,
                    "root_cause": report.root_cause[:200],
                },
            ))
        else:
            await investigation_store.update_investigation(
                investigation_id,
                status=InvestigationStatus.FAILED,
                error="Failed to parse investigation report",
            )

    async def _handle_fix_complete(
        self, investigation_id: str, session_id: str, session: dict, messages: list[dict]
    ) -> None:
        """Handle completion of a fix session."""
        investigation = investigation_store.get_investigation(investigation_id)
        if not investigation:
            return

        # Try to find PR URL from session or messages
        pr_url = session.get("pull_request_url", None)
        if not pr_url:
            full_text = "\n".join(
                m.get("content", "") or m.get("message", "") or ""
                for m in messages if isinstance(m, dict)
            )
            pr_match = re.search(r"https://github\.com/[^\s]+/pull/\d+", full_text)
            if pr_match:
                pr_url = pr_match.group(0)

        # Mark all fix telemetry steps as completed
        for step in investigation.telemetry:
            if step.status != "completed":
                await investigation_store.update_telemetry_step(
                    investigation_id, step.id, "completed"
                )

        # Move to PENDING_REVIEW instead of RESOLVED — user must manually approve
        await investigation_store.update_investigation(
            investigation_id,
            status=InvestigationStatus.PENDING_REVIEW,
            pr_url=pr_url,
            completed_at=time.time(),
            elapsed_seconds=time.time() - (investigation.started_at or investigation.created_at),
        )

        await event_bus.publish(SSEEvent(
            event_type="fix_pending_review",
            investigation_id=investigation_id,
            data={"pr_url": pr_url},
        ))


# Singleton
session_poller = SessionPoller()
