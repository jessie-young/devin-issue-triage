# Simulation vs Real: Component Status

This document identifies every component that has simulation, mock, or hardcoded behavior and describes what needs to change for a fully working live demo.

---

## Component Inventory

### 1. Devin API — Session Creation (Investigation)

**Classification: SIMULATION**

- **What it does now:** When `DEVIN_API_KEY` and `DEVIN_ORG_ID` are not set, `devin_client.create_investigation_session()` raises an exception (no mock fallback in the client itself). The webhook handler catches that exception and falls back to calling the `/investigations/simulate/{id}` endpoint, which populates the investigation with pre-built investigation data from a keyword-matching lookup table in `_get_simulation_data:_get_simulation_data()`.
- **What needs to change:** Set `DEVIN_API_KEY` and `DEVIN_ORG_ID` environment variables on the Fly.io backend. The real code path in `devin_client.py` already constructs the correct Devin API v3 org-scoped request to `POST /organizations/{org_id}/sessions`.
- **What's needed:**
  - A Devin Service User with `ManageOrgSessions` permission (create at Settings → Service Users)
  - `fly secrets set DEVIN_API_KEY=cog_xxx DEVIN_ORG_ID=org-xxx -a app-ehojkbnz`

### 2. Devin API — Session Creation (Fix)

**Classification: SIMULATION**

- **What it does now:** `launch_fix()` in `_get_simulation_data` calls `devin_client.create_fix_session()`. If that fails, it falls back to `_simulate_fix()` — an async task that sleeps through 5 telemetry steps (1.5s each) and marks the investigation as complete. The `pr_url` is set to the issue URL (not a real PR).
- **What needs to change:** With valid Devin API credentials, the real code path creates a Devin session with the fix prompt. The session poller then tracks real progress. A real PR URL comes from Devin's actual PR creation.
- **What's needed:** Same Devin API credentials as above.

### 3. Devin API — Session Polling & Telemetry Extraction

**Classification: SIMULATION**

- **What it does now:** `session_poller.py` has full implementation for polling Devin sessions (`GET /sessions/{id}` and `GET /sessions/{id}/messages`), parsing messages for telemetry keywords, and extracting structured investigation reports. However, since no real sessions exist in simulation mode, this code path is never exercised. Instead, telemetry steps are marked complete instantly by `simulate_investigation()`.
- **What needs to change:** No code changes needed. Once real Devin sessions are created, the poller automatically starts tracking them via `session_poller.start_polling()`.
- **What's needed:** Valid Devin API credentials.

### 4. GitHub Webhook

**Classification: REAL**

- **What it does now:** The webhook endpoint at `/webhooks/github` is live and connected to `jessie-young/demo-finserv-repo`. It receives real `issues` events (opened/labeled), verifies signatures if configured, and creates investigations. When the Devin API is unavailable, it falls back to simulated investigation.
- **What needs to change:** Nothing for the webhook itself — it works end-to-end. For real investigations, Devin API credentials need to be set.
- **What's needed:** Webhook is already configured at `https://app-ehojkbnz.fly.dev/webhooks/github`.

### 5. GitHub Comment Posting

**Classification: PARTIAL**

- **What it does now:** `github_service.post_investigation_comment()` makes real GitHub API calls using `GITHUB_PAT` to post formatted investigation reports on issues. This is called from:
  - `simulate_investigation()` — posts real comments with simulated investigation data
  - `session_poller._handle_investigation_complete()` — would post comments with real investigation data
- **Real parts:** The GitHub API call is real. Comments are actually posted to GitHub issues.
- **Simulated parts:** The investigation data in the comments comes from the hardcoded simulation lookup table, not from real Devin analysis.
- **What needs to change:** Once Devin API is connected, comments will contain real investigation findings.
- **What's needed:** `GITHUB_PAT` is already set and working.

### 6. PR Creation

**Classification: SIMULATION**

- **What it does now:** In simulation mode, the `pr_url` on completed STRIKE investigations is set to the GitHub issue URL (e.g., `https://github.com/.../issues/5`). No real PR is created. The "View Pull Request" link on the dashboard points to the issue page.
- **What needs to change:** When Devin API is connected and a fix session runs, Devin will create a real PR on the repo. The session poller extracts the PR URL from Devin's messages and sets it on the investigation.
- **What's needed:** Devin API credentials + the target repo must be connected to Devin's GitHub integration.

### 7. SSE Streaming

**Classification: REAL**

- **What it does now:** The `event_bus.py` SSE system is fully real. Events are published to an in-memory queue, and the dashboard connects to `/investigations/stream` via `EventSource`. Events flow in real time — investigation created, telemetry updates, investigation complete, investigation resolved.
- **What needs to change:** Nothing. SSE works the same whether the underlying data is simulated or real.
- **What's needed:** Already working.

### 8. Telemetry Parsing (from Devin Messages)

**Classification: SIMULATION**

- **What it does now:** `session_poller.py` contains keyword-based telemetry parsing logic (`TELEMETRY_KEYWORDS` dict) that matches Devin's message content to investigation steps (scan, files, git, root_cause, classify). In simulation mode, this is bypassed — steps are marked complete directly by `simulate_investigation()`.
- **What needs to change:** No code changes. Once real sessions exist, the poller parses real Devin messages.
- **What's needed:** Devin API credentials.

### 9. Pre-seeded Dashboard Data

**Classification: SIMULATION**

- **What it does now:** On startup, `main.py` calls `/investigations/ingest-all` to fetch all open GitHub issues via the real GitHub API, then calls `/investigations/simulate/{id}` for each to populate them with hardcoded investigation results from `_get_simulation_data()`. ASSIST/COMMAND investigations are routed to the Completed column. This gives the dashboard a rich initial state.
- **What needs to change:** For a live demo, you would run real Devin investigations against all issues before the demo (by temporarily enabling the Devin API and triggering investigations). The auto-seed logic would be disabled or replaced.
- **What's needed:** Run investigations ahead of time, or keep simulation for demo purposes.

### 10. Metrics / Charts

**Classification: PARTIAL**

- **What it does now:** The MetricsPanel computes all charts dynamically from the actual investigation data in the dashboard state:
  - Classification distribution (pie chart) — computed from real classification counts
  - Issues by module (bar chart) — computed from `relevant_files` in investigation reports
  - Issues resolved over time (bar chart) — computed from `completed_at` timestamps
  - Backlog trajectory (line chart) — computed from cumulative created vs completed
- **Real parts:** Chart logic is real and data-driven. No hardcoded chart data.
- **Simulated parts:** The underlying investigation data is from simulation, so the charts reflect simulated investigation results.
- **What needs to change:** Nothing in the chart code. Charts will automatically reflect real data once investigations are real.
- **What's needed:** Real investigation data.

### 11. Playbook / Knowledge Note Creation

**Classification: REAL (when credentials provided)**

- **What it does now:** `setup_devin.py` makes real HTTP calls to the Devin API v3 to create:
  - Investigation playbook (`POST /organizations/{org_id}/playbooks`)
  - Fix playbook (`POST /organizations/{org_id}/playbooks`)
  - Knowledge note (`POST /organizations/{org_id}/knowledge`)
  - Daily triage schedule (`POST /organizations/{org_id}/schedules`)
- The script requires `DEVIN_API_KEY` and `DEVIN_ORG_ID` env vars and exits with an error if they're missing.
- **What needs to change:** Run the script once with valid credentials.
- **What's needed:** `DEVIN_API_KEY=cog_xxx DEVIN_ORG_ID=org-xxx python -m app.scripts.setup_devin`

### 12. Schedule Creation (Daily Triage)

**Classification: REAL (when credentials provided)**

- **What it does now:** `setup_devin.py` creates a schedule via `POST /organizations/{org_id}/schedules` with cron `0 9 * * 1-5` (9 AM weekdays ET). This is a real API call.
- **What needs to change:** Run the setup script.
- **What's needed:** Same Devin API credentials.

### 13. Manual "Add Issue" Trigger

**Classification: REAL**

- **What it does now:** The dashboard's "Add Issue" input calls `POST /investigations/file` with an issue URL or number. The orchestrator fetches the real issue from GitHub, creates an investigation, and attempts to start a Devin investigation (falling back to simulation if unavailable).
- **What needs to change:** Nothing — works end-to-end in both modes.
- **What's needed:** Already working.

---

## Summary Table

| Component | Status | Blocking On |
|---|---|---|
| GitHub Webhook Receiver | **REAL** | Nothing |
| SSE Streaming | **REAL** | Nothing |
| Manual Trigger | **REAL** | Nothing |
| GitHub Comment Posting | **PARTIAL** | Comments are real; investigation data is simulated |
| Metrics / Charts | **PARTIAL** | Charts are real; underlying data is simulated |
| Playbooks / Knowledge / Schedules | **REAL** (needs credentials) | `DEVIN_API_KEY`, `DEVIN_ORG_ID` |
| Devin Investigation Sessions | **SIMULATION** | `DEVIN_API_KEY`, `DEVIN_ORG_ID` |
| Devin Fix Sessions | **SIMULATION** | `DEVIN_API_KEY`, `DEVIN_ORG_ID` |
| Telemetry Parsing | **SIMULATION** | `DEVIN_API_KEY`, `DEVIN_ORG_ID` |
| PR Creation | **SIMULATION** | `DEVIN_API_KEY`, `DEVIN_ORG_ID`, repo connected to Devin |
| Pre-seeded Data | **SIMULATION** | Run real investigations before demo |

---

## Path to Live Demo

In priority order, here is exactly what needs to happen to go from the current state to a fully working live demo:

### Step 1: Create Devin Service User (5 min)
1. Go to https://app.devin.ai/settings → **Service Users**
2. Click **Create Service User**, name it `issue-triage-bot`
3. Grant `ManageOrgSessions` permission
4. Copy the API key (`cog_...`) and note the Org ID (`org-...`)

### Step 2: Set Environment Variables on Fly.io (1 min)
```bash
fly secrets set DEVIN_API_KEY=cog_xxx DEVIN_ORG_ID=org-xxx -a app-ehojkbnz
```
This immediately enables real Devin sessions. The code already handles both paths.

### Step 3: Run Setup Script to Create Playbooks + Knowledge + Schedule (2 min)
```bash
DEVIN_API_KEY=cog_xxx DEVIN_ORG_ID=org-xxx python -m app.scripts.setup_devin
```
This creates:
- Investigation playbook (FinServ Bug Investigation Protocol)
- Fix playbook (FinServ Bug Fix Protocol)
- Knowledge note (FinServ Platform Codebase Context)
- Daily triage schedule (9 AM weekdays)

### Step 4: Connect Target Repo to Devin (2 min)
Ensure `jessie-young/demo-finserv-repo` is accessible to Devin's GitHub integration so that Devin sessions can clone the repo and create PRs.

### Step 5: Pre-seed with Real Investigations (30-60 min)
Before the demo, trigger real investigations for all 19 existing issues:
1. Temporarily disable auto-seed in `main.py` (comment out the seed block)
2. Use the "Add Issue" button on the dashboard, or call `POST /investigations/ingest-all` followed by individual investigation triggers
3. Wait for all Devin sessions to complete
4. The dashboard will fill with real investigation data, real comments on GitHub issues, and real classifications

### Step 6: Live Demo
1. Open the dashboard — it shows pre-seeded completed investigations
2. File a new GitHub issue on `demo-finserv-repo`
3. The webhook triggers a real Devin investigation → dashboard shows live telemetry
4. When investigation completes, click "Apply Fix" on a STRIKE investigation
5. Devin creates a real PR → "View Pull Request" links to the actual PR

### Optional: Machine Snapshots
For faster Devin session startup, configure a machine snapshot with the repo pre-cloned and dependencies installed. This is a nice-to-have optimization mentioned in the plan.
