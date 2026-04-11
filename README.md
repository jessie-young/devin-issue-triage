# Mission Control

A NASA Mission Control-themed automation system that watches a GitHub repo for new issues, automatically dispatches Devin to investigate each one, displays real-time investigation telemetry on a dashboard, and lets an engineering lead click "GO FOR LAUNCH" to have Devin autonomously fix bugs and open PRs.

## Architecture

```
mission-control/
  orchestrator/   # Python/FastAPI backend — webhook receiver, Devin API client, SSE streaming
  dashboard/      # React/Vite frontend — NASA-themed Mission Control UI
```

## Orchestrator (Python/FastAPI)

The orchestrator connects GitHub webhooks to the Devin API and streams real-time updates to the dashboard.

### Key Components
- **Webhook Receiver** — Listens for GitHub `issues` events
- **Devin API Client** — Creates investigation and fix sessions
- **Session Poller** — Polls active Devin sessions for progress telemetry
- **Mission Classifier** — Routes missions as STRIKE / ASSIST / COMMAND
- **GitHub Commenter** — Posts investigation reports back to issues
- **Launch Handler** — Creates fix sessions when user clicks GO FOR LAUNCH
- **SSE Endpoint** — Streams real-time telemetry to the dashboard

### Setup
```bash
cd orchestrator
poetry install
cp .env.example .env  # Fill in DEVIN_API_TOKEN and GITHUB_TOKEN
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Dashboard (React/Vite)

A NASA Mission Control-themed React app showing real-time investigation telemetry.

### Features
- Dark navy/charcoal background with glowing teal/cyan active elements
- Three-column layout: Mission Queue, Active Missions, Completed Missions
- Animated telemetry timeline showing investigation steps
- GO FOR LAUNCH button for auto-fixable (STRIKE) missions
- Scrolling telemetry strip with raw event log
- SSE connection with auto-reconnect

### Setup
```bash
cd dashboard
npm install
cp .env.example .env  # Set VITE_API_URL to orchestrator URL
npm run dev
```

## Mission Classifications

| Classification | Meaning | Action |
|---|---|---|
| **STRIKE** | Auto-fixable with high confidence | GO FOR LAUNCH available |
| **ASSIST** | Needs human guidance | Briefing posted to issue |
| **COMMAND** | Requires senior/architectural decision | Routed to team lead |

## Demo Target Repo

The system is configured to work with [demo-finserv-repo](https://github.com/jessie-young/demo-finserv-repo) — a sample financial services monorepo with planted bugs for demonstration.
