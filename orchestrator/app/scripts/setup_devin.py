"""Setup scripts for creating Devin playbooks, knowledge notes, and schedules.

Run these scripts to configure Devin for the Issue Triage workflow.
Requires DEVIN_API_KEY and DEVIN_ORG_ID environment variables.

Usage:
    DEVIN_API_KEY=cog_xxx DEVIN_ORG_ID=org-xxx python -m app.scripts.setup_devin
"""

from __future__ import annotations

import json
import os
import sys

import httpx

DEVIN_API_BASE = os.environ.get("DEVIN_API_BASE_URL", "https://api.devin.ai/v3")
DEVIN_API_KEY = os.environ.get("DEVIN_API_KEY", "")
DEVIN_ORG_ID = os.environ.get("DEVIN_ORG_ID", "")
TARGET_REPO = os.environ.get("TARGET_REPO", "jessie-young/demo-finserv-repo")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DEVIN_API_KEY}",
        "Content-Type": "application/json",
    }


def _org_url(path: str) -> str:
    """Build organization-scoped API URL."""
    return f"{DEVIN_API_BASE}/organizations/{DEVIN_ORG_ID}{path}"


INVESTIGATION_PLAYBOOK = {
    "name": "FinServ Bug Investigation Protocol",
    "description": "Structured investigation protocol for FinServ Platform issues. Devin follows this playbook to scan the codebase, trace git history, identify root cause, assess complexity, and classify the investigation as AUTO_FIX/NEEDS_REVIEW/ESCALATE.",
    "content": """# FinServ Bug Investigation Protocol

## Objective
Investigate the reported issue systematically and produce a structured investigation report.

## Steps

### 1. Issue Ingestion
- Read the GitHub issue carefully
- Identify keywords, error messages, module names, and affected functionality

### 2. Codebase Scan
- Search the repository for files related to the issue
- Focus on the relevant module (payments, accounts, auth, transactions, notifications, reporting)
- Check shared utilities in `src/shared/utils/`
- Check legacy code in `src/legacy/` if relevant

### 3. Identify Relevant Files
- List all files that could be related to the bug
- Include controllers, services, repositories, and test files
- Check for shared dependencies

### 4. Git History Analysis
- Run `git log` on relevant files
- Run `git blame` on suspicious code sections
- Identify which commit introduced the bug
- Note the author and date

### 5. Root Cause Analysis
- Determine the exact cause of the bug
- Identify the specific line(s) of code
- Explain the mechanism (why does this code fail?)

### 6. Complexity Assessment
Rate as low / medium / high:
- **Low**: Single file change, clear fix, no regression risk
- **Medium**: Multiple files or trade-offs involved
- **High**: Architectural change needed, cross-cutting concern

### 7. Fix Confidence Score (1-100)
- 90-100: Simple, unambiguous fix
- 70-89: Straightforward with minor decisions
- 50-69: Possible but involves trade-offs
- Below 50: Needs human input

### 8. Classification
- **AUTO_FIX** (confidence >= 80, low/medium complexity): Auto-fixable
- **NEEDS_REVIEW** (confidence 50-79 or medium with trade-offs): Human review needed
- **ESCALATE** (confidence < 50 or high complexity): Senior decision required

### 9. Related Issues
- Check for other open issues that might share the same root cause

## Output Format
```
INVESTIGATION REPORT
====================
RELEVANT FILES: [file paths]
GIT HISTORY: [relevant commits]
ROOT CAUSE: [detailed explanation]
COMPLEXITY: [low/medium/high]
FIX CONFIDENCE: [1-100]
CLASSIFICATION: [AUTO_FIX/NEEDS_REVIEW/ESCALATE]
RELATED ISSUES: [issue numbers or "none"]
SUMMARY: [2-3 sentences]
RECOMMENDED FIX: [description]
```
""",
}

FIX_PLAYBOOK = {
    "name": "FinServ Bug Fix Protocol",
    "description": "Protocol for fixing bugs in the FinServ Platform. Follows coding standards: TypeScript strict, integer cents for money, regression tests required.",
    "content": """# FinServ Bug Fix Protocol

## Objective
Implement a fix for the identified bug, write a regression test, and open a PR.

## Coding Standards
- TypeScript strict mode
- Use integer cents for all monetary amounts (multiply by 100, never use floating point for money)
- Follow existing code patterns in neighboring files
- Keep changes minimal and focused

## Steps

### 1. Write the Fix
- Implement the code change described in the investigation report
- Follow existing patterns in the codebase
- Add inline comments explaining the fix if the change isn't obvious

### 2. Write Regression Test
- Add a test in the module's `__tests__/` directory
- The test should fail without the fix and pass with it
- Follow existing test patterns (Jest)

### 3. Run Test Suite
- Execute `npm test`
- Ensure all tests pass (new and existing)
- Fix any test failures

### 4. Open PR
- Create a branch named `fix/issue-{number}-{short-description}`
- Commit with message: `fix: {description} (fixes #{issue_number})`
- Open a PR with clear description referencing the issue
- Include: what changed, why, and how to test
""",
}

KNOWLEDGE_NOTE = {
    "name": "FinServ Platform Codebase Context",
    "content": f"""# FinServ Platform — Codebase Context

## Repository
- **Repo**: {TARGET_REPO}
- **Stack**: TypeScript / Express / Node.js
- **Architecture**: Modular monolith with controller/service/repository pattern

## Modules
- `src/modules/accounts/` — Account management, balance operations
- `src/modules/auth/` — JWT authentication, token management
- `src/modules/payments/` — Payment processing, fee calculation
- `src/modules/transactions/` — Transaction listing, pagination, filtering
- `src/modules/notifications/` — Email notifications, templates
- `src/modules/reporting/` — Report generation, CSV export

## Shared Code
- `src/shared/utils/` — Currency formatting, date helpers, validators
- `src/shared/middleware/` — Error handler, rate limiter, auth middleware
- `src/shared/types/` — Shared TypeScript types

## Legacy Code
- `src/legacy/bridge.js` — Legacy API compatibility bridge
- `src/legacy/migration-utils.js` — Data migration utilities

## Team (Historical)
- **Sarah Chen** (Senior) — Core architecture, auth, shared utilities
- **Marcus Johnson** (Mid-Level) — Transactions, reporting
- **Alex Rivera** (Junior) — Accounts, notifications
- **Priya Patel** (Former) — Payments, legacy bridge

## Known Tech Debt
- Floating-point money calculations in payments module
- Race condition in account balance updates (no DB locking)
- JWT refresh tokens not invalidated on use
- Legacy bridge has no timeout configuration
- Date utilities don't handle DST correctly

## Conventions
- Tests in `__tests__/` directories within each module
- Controller handles HTTP, service handles business logic, repository handles data
- All monetary amounts should be in integer cents
- TypeScript strict mode enabled
""",
}


def create_playbook(playbook_data: dict) -> None:
    """Create a Devin playbook via the API."""
    print(f"Creating playbook: {playbook_data['name']}...")
    try:
        resp = httpx.post(
            _org_url("/playbooks"),
            headers=_headers(),
            json=playbook_data,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"  Created: {result.get('id', 'unknown')}")
    except Exception as e:
        print(f"  Error: {e}")


def create_knowledge_note(note_data: dict) -> None:
    """Create a Devin knowledge note via the API."""
    print(f"Creating knowledge note: {note_data['name']}...")
    try:
        resp = httpx.post(
            _org_url("/knowledge"),
            headers=_headers(),
            json=note_data,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"  Created: {result.get('id', 'unknown')}")
    except Exception as e:
        print(f"  Error: {e}")


def create_scheduled_session() -> None:
    """Create a daily morning triage session."""
    print("Creating daily triage schedule...")
    schedule_data = {
        "name": "FinServ Morning Bug Triage",
        "description": "Daily automated triage of new GitHub issues on the FinServ Platform",
        "cron": "0 9 * * 1-5",  # 9 AM weekdays
        "prompt": f"Review all open issues on {TARGET_REPO} that were created in the last 24 hours. "
                  f"For each new issue, follow the FinServ Bug Investigation Protocol playbook.",
        "timezone": "America/New_York",
    }
    try:
        resp = httpx.post(
            _org_url("/schedules"),
            headers=_headers(),
            json=schedule_data,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"  Created: {result.get('id', 'unknown')}")
    except Exception as e:
        print(f"  Error: {e}")


def main():
    if not DEVIN_API_KEY:
        print("ERROR: DEVIN_API_KEY environment variable not set")
        print("  Create a service user at https://app.devin.ai/settings")
        sys.exit(1)
    if not DEVIN_ORG_ID:
        print("ERROR: DEVIN_ORG_ID environment variable not set")
        print("  Find your org ID at https://app.devin.ai/settings → Service Users")
        sys.exit(1)

    print(f"Setting up Devin for {TARGET_REPO}...")
    print(f"API Base: {DEVIN_API_BASE}")
    print(f"Org ID: {DEVIN_ORG_ID}")
    print()

    create_playbook(INVESTIGATION_PLAYBOOK)
    print()
    create_playbook(FIX_PLAYBOOK)
    print()
    create_knowledge_note(KNOWLEDGE_NOTE)
    print()
    create_scheduled_session()
    print()
    print("Setup complete!")


if __name__ == "__main__":
    main()
