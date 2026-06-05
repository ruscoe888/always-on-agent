# Plan 2 — Multi-Agent Architecture & Live Feed

## The Problem With Cron-Only

The current setup uses a single Claude Code durable cron running every 4 hours. This works for batch analysis but has three structural limits:

| Limit | Impact |
|---|---|
| **4-hour polling gap** | A P0 filed at 00:18 sits untriaged until 04:17 |
| **Single agent does everything** | Triage, correlation, compliance, and GitHub writes all in one context — slow, no specialisation |
| **7-day TTL** | Cron expires and must be manually renewed |
| **No live feed** | Dashboard only shows what's already been filed — nothing "incoming" |

Plan 2 fixes all of these by splitting into specialised agents and adding a real-time feed layer.

---

## The Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    REPO (Source of Truth)                    │
│  issues/   deploys/   runbooks/   contracts/   CLAUDE.md    │
└──────────────────────┬──────────────────────────────────────┘
                       │  git push triggers
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              GitHub Actions (Event-Driven Layer)             │
│                                                             │
│  on: push → issues/**    on: schedule (hourly)              │
│       ↓                         ↓                           │
│  Triage Agent            Compliance Agent                    │
│  Correlation Agent       Fabricator Agent (dev/staging only) │
└──────────────────────┬──────────────────────────────────────┘
                       │  gh issue create
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  GitHub Issues (Output)                      │
│  Labels: ops-agent, agent-triage, agent-correlation,        │
│          agent-compliance, agent-fabricated                  │
└──────────────────────┬──────────────────────────────────────┘
                       │  GitHub API (polling)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Dashboard (dashboard/index.html)                │
│  30s auto-refresh + live activity chart                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Agent Roster — One Job Each

### Agent 1: Watcher (replaces the cron)
**Trigger:** GitHub Actions `on: push` to `issues/**`
**Job:** Detects new JSON files pushed to `issues/`. Immediately runs triage and correlation on the new issue only. Does not re-scan existing issues.
**Why better than cron:** Sub-minute response time. P0 filed → triage issue opened in under 60 seconds.
**File:** `.github/workflows/agent-watcher.yml`

### Agent 2: Triage Agent
**Trigger:** Called by Watcher on new issue push, or by Scheduler hourly for any unprocessed issues.
**Job:** Reads a single issue JSON. Assigns severity. Matches runbook. Recommends on-call. Opens one GitHub Issue.
**Specialisation:** Only does triage — fast, focused context window.
**File:** `agents/triage-agent.md` (CLAUDE.md for this agent)

### Agent 3: Correlation Agent
**Trigger:** Called by Watcher after Triage Agent completes.
**Job:** Reads the new issue + `deploys/recent.json`. Finds deploy correlations within 48h. Opens a correlation GitHub Issue if found.
**Specialisation:** Only does correlation — reads two files, writes one issue.
**File:** `agents/correlation-agent.md`

### Agent 4: Compliance Agent
**Trigger:** GitHub Actions `on: schedule` — runs once daily at 06:00 UTC.
**Job:** Full audit of all contracts against `compliance-policy.md`. Only opens issues for violations not already filed.
**Frequency:** Daily (not every push) — contracts change slowly.
**File:** `agents/compliance-agent.md`

### Agent 5: Fabricator Agent
**Trigger:** GitHub Actions `on: schedule` — runs every 20 minutes (dev/staging only).
**Job:** Calls `scripts/fabricate-issue.py` to push a new synthetic issue. This feeds the live dashboard.
**Scope:** Disabled in production. Controlled by a repo variable `FABRICATION_ENABLED`.
**File:** `.github/workflows/agent-fabricator.yml`

### Agent 6: Keeper Agent (new)
**Trigger:** GitHub Actions `on: schedule` — weekly.
**Job:** Audits the agent ecosystem itself. Checks: are all workflows still enabled? Is the compliance policy up to date? Are any runbooks older than 90 days without a review? Opens GitHub Issues for governance gaps.
**File:** `.github/workflows/agent-keeper.yml`

---

## Why GitHub Actions Over Claude Code Cron

| Dimension | Claude Code Cron | GitHub Actions |
|---|---|---|
| **Trigger** | Time-based only | Push events + schedule |
| **TTL** | 7 days, manual renewal | Runs until disabled |
| **Machine dependency** | Requires Claude Code running locally | Runs in GitHub cloud |
| **Cost** | Included in Claude Code | GitHub-hosted runners: free tier 2,000 min/month |
| **Latency** | Up to 4h | Under 60s on push trigger |
| **Observability** | Run logs in Claude Code terminal | Full logs in GitHub Actions UI |
| **Secret management** | Local env vars | GitHub Secrets (encrypted) |

**Recommendation:** Migrate to GitHub Actions for production. Keep Claude Code cron for local development and ad-hoc runs.

---

## Implementation Sequence

### Phase 1 (Now — Claude Code cron, current state)
- ✅ Single durable cron, every 4h
- ✅ All three tasks in one CLAUDE.md
- ✅ Manual issue fabrication

### Phase 2 (Next sprint — split agents, GitHub Actions)
1. Create `agents/` directory with per-agent CLAUDE.md files
2. Add `.github/workflows/agent-watcher.yml` (push trigger)
3. Add `.github/workflows/agent-compliance.yml` (daily schedule)
4. Add `.github/workflows/agent-fabricator.yml` (20-min schedule, dev only)
5. Add `ANTHROPIC_API_KEY` to GitHub Secrets
6. Test end-to-end: push a new issue JSON → watch triage issue appear in <60s

### Phase 3 (Future — full autonomy)
- Keeper Agent for governance
- Slack/PagerDuty webhook for P0s
- Auto-close stale issues older than 30 days
- PR-based review gate for CLAUDE.md changes

---

## The Live Feed Question

**Can the dashboard show truly live data?**

The dashboard reads the GitHub Issues API. GitHub updates instantly when an issue is created. The limitation is polling frequency:
- Current: `init()` runs once on page load
- Plan 2: Auto-refresh every 30 seconds + a live activity chart showing issues as they arrive

The live activity chart (added in dashboard v2) shows a rolling 60-minute timeline of issue creation events. Each new issue appears as a pulse on the chart within 30 seconds of the agent filing it.

**Why not WebSockets?** GitHub doesn't offer a WebSocket API for issues. Polling at 30s is the practical maximum without hitting rate limits (60 unauthenticated requests/hour = one every 60s; authenticated = 5,000/hour).

---

## Secrets Required

| Secret | Where | Used by |
|---|---|---|
| `ANTHROPIC_API_KEY` | GitHub Secrets | All Claude-powered agents in Actions |
| `GH_PAT` | GitHub Secrets | Agents that create issues (if default GITHUB_TOKEN is insufficient) |
| `FABRICATION_ENABLED` | GitHub Variables | Fabricator Agent — set `true` only in dev |
