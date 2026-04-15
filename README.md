# Devin Issue Triage

An automated issue investigation and resolution system that watches a GitHub repo for new issues, dispatches Devin to investigate each one, displays real-time progress on a dashboard, and lets an engineering lead approve fixes that Devin implements and opens as PRs.

## Architecture

```
devin-issue-triage/
  orchestrator/   # Python/FastAPI backend — webhook receiver, Devin API client, SSE streaming
  dashboard/      # React/Vite frontend — professional issue triage dashboard
```

## Orchestrator (Python/FastAPI)

The orchestrator connects GitHub webhooks to the Devin API and streams real-time updates to the dashboard.

### Key Components
- **Webhook Receiver** — Listens for GitHub `issues` events
- **Devin API Client** — Creates investigation and fix sessions
- **Session Poller** — Polls active Devin sessions for progress telemetry
- **Issue Classifier** — Routes issues as Auto-fix / Needs Review / Escalate
- **GitHub Commenter** — Posts investigation reports back to issues
- **Fix Handler** — Creates fix sessions when user clicks Apply Fix
- **SSE Endpoint** — Streams real-time telemetry to the dashboard

### Setup
```bash
cd orchestrator
poetry install
cp .env.example .env  # Fill in DEVIN_API_KEY, DEVIN_ORG_ID, and GITHUB_TOKEN
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Dashboard (React/Vite)

A clean, professional dashboard showing real-time investigation progress.

### Features
- Three-column layout: Queue, In Progress, Resolved
- Step-by-step investigation timeline with real-time updates
- Apply Fix button for auto-fixable issues
- Metrics panel with charts (classification, module distribution, resolved over time, backlog)
- Activity log with timestamped events
- SSE connection with auto-reconnect

### Setup
```bash
cd dashboard
npm install
cp .env.example .env  # Set VITE_API_URL to orchestrator URL
npm run dev
```

## Issue Classifications

| Classification | Meaning | Action |
|---|---|---|
| **Auto-fix** | High confidence, auto-fixable | Apply Fix available |
| **Needs Review** | Needs human guidance | Briefing posted to issue |
| **Escalate** | Requires senior/architectural decision | Routed to team lead |

## Demo Target Repo

The system is configured to work with [demo-finserv-repo](https://github.com/jessie-young/demo-finserv-repo) — a sample financial services monorepo with planted bugs for demonstration.
