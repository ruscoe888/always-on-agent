# Agent Roster — Who Does What

This document defines every agent in the ops system, its single responsibility, its trigger, and how to extend or debug it.

---

## Design Principle: One Agent, One Job

Each agent has a bounded context:
- Reads the minimum data it needs
- Writes exactly one type of output
- Cannot interfere with another agent's domain
- Can be tested, replaced, or upgraded independently

---

## Current Agents (Plan 1 — Claude Code Cron)

### 🦇 Ops Agent (Monolith)
| Property | Value |
|---|---|
| **Status** | Active |
| **Trigger** | Claude Code durable cron — every 4h at :17 |
| **Reads** | All issues, deploys, runbooks, contracts, compliance-policy.md |
| **Writes** | GitHub Issues: triage + correlation + compliance |
| **Protocol** | `CLAUDE.md` (root of repo) |
| **Cron ID** | `5a9ff4c4` |
| **TTL** | 7 days from creation — must renew |
| **Dedup** | Queries `gh issue list --label ops-agent` before creating |

**Renew command:**
```
Create a durable recurring cron (17 */4 * * *, durable: true) with prompt:
"cd /Users/pruscoe/Claude/hackathon, git pull, follow CLAUDE.md Ops Agent Run Protocol"
```

---

## Planned Agents (Plan 2 — Specialised, GitHub Actions)

### 1. 👁 Watcher Agent
| Property | Value |
|---|---|
| **Status** | Planned |
| **Trigger** | `on: push` to `issues/**` |
| **Reads** | The new issue file only |
| **Writes** | Dispatches Triage + Correlation agents |
| **File** | `.github/workflows/agent-watcher.yml` |
| **Latency** | <60s from git push |
| **Why it exists** | Replaces the 4-hour polling gap with event-driven response |

### 2. 🩺 Triage Agent
| Property | Value |
|---|---|
| **Status** | Planned |
| **Trigger** | Called by Watcher on new issue; or Scheduler hourly for backlog |
| **Reads** | Single issue JSON + `runbooks/` |
| **Writes** | One `[Agent Triage]` GitHub Issue |
| **File** | `agents/triage-agent.md`, `.github/workflows/agent-triage.yml` |
| **Context window** | Small — one issue + three runbook files |
| **Dedup** | Checks for existing `[Agent Triage] PROD-XXXX` title |

**Severity rubric:**
- P0: Active outage, multiple customers, revenue impact
- P1: Single enterprise customer, significant degradation
- P2: Intermittent, workaround available
- P3: Feature request, no urgency

### 3. 🔗 Correlation Agent
| Property | Value |
|---|---|
| **Status** | Planned |
| **Trigger** | Called by Watcher after Triage Agent; or Scheduler hourly |
| **Reads** | Single issue JSON + `deploys/recent.json` |
| **Writes** | One `[Agent Correlation]` GitHub Issue (if correlation found) |
| **File** | `agents/correlation-agent.md`, `.github/workflows/agent-correlation.yml` |
| **Logic** | 48-hour window, service-area keyword matching, causal chain detection |
| **Dedup** | Checks for existing `[Agent Correlation] PROD-XXXX` title |

### 4. ⚖️ Compliance Agent
| Property | Value |
|---|---|
| **Status** | Planned |
| **Trigger** | Daily at 06:00 UTC (`on: schedule: cron: '0 6 * * *'`) |
| **Reads** | `contracts/*.md` + `compliance-policy.md` |
| **Writes** | One GitHub Issue per new violation found |
| **File** | `agents/compliance-agent.md`, `.github/workflows/agent-compliance.yml` |
| **Frequency** | Daily — contracts change slowly |
| **Dedup** | Checks for existing `[Agent Compliance] <contract>: <rule>` title |

### 5. 🔧 Fabricator Agent
| Property | Value |
|---|---|
| **Status** | Active (Claude Code cron) |
| **Trigger** | Manual (`python3 scripts/fabricate-issue.py`) or cron |
| **Reads** | `issues/` (to find the highest PROD-ID) |
| **Writes** | A new `issues/PROD-XXXX.json` + git commit + push |
| **File** | `scripts/fabricate-issue.py` |
| **Labels** | `agent-fabricated` (to distinguish from real issues) |
| **Scope** | Dev/staging only. Disable via `FABRICATION_ENABLED=false` repo variable in production |

**Run manually:**
```bash
python3 scripts/fabricate-issue.py
```

**Run on a schedule (Claude Code):**
```
CronCreate: "*/20 * * * *", durable: true, prompt:
"Run: python3 /Users/pruscoe/Claude/hackathon/scripts/fabricate-issue.py"
```

### 6. 🔑 Keeper Agent
| Property | Value |
|---|---|
| **Status** | Planned |
| **Trigger** | Weekly on Monday 08:00 UTC |
| **Reads** | `.github/workflows/`, `agents/`, `runbooks/`, `CLAUDE.md` |
| **Writes** | GitHub Issues for governance gaps |
| **File** | `agents/keeper-agent.md`, `.github/workflows/agent-keeper.yml` |

**What it checks:**
- Are all scheduled workflows running? (no missed executions in the last 7 days)
- Are any runbooks older than 90 days without a git commit?
- Is `compliance-policy.md` older than 180 days? (may need legal review)
- Is the dedup issue list growing unboundedly? (>500 open ops-agent issues = signal to clean up)
- Is the Fabricator Agent disabled in production? (check repo variable)

---

## Agent Communication Protocol

Agents do not call each other directly. They communicate via the shared state:

```
Git repo (source of truth)
    ↓ push
GitHub Actions (orchestration)
    ↓ issue create
GitHub Issues (findings)
    ↓ API poll
Dashboard (visibility)
```

This means:
- **No agent-to-agent API calls** — loose coupling, no cascading failures
- **GitHub Issues are the message bus** — dedup is title-matching, not a shared DB
- **Any agent can be added or removed** without affecting others
- **Replay is free** — re-run any workflow on any issue to regenerate its findings

---

## Adding a New Agent

1. Create `agents/<name>-agent.md` with the agent's CLAUDE.md-style protocol
2. Create `.github/workflows/agent-<name>.yml` with the trigger and Claude invocation
3. Add a label in GitHub for the agent's output (e.g., `agent-name`)
4. Add the label to the dashboard's filter list
5. Document in this file under "Planned Agents"
6. Add the `Bash(...)` commands the agent needs to the global allowlist

---

## Allowlist Reference

All agents share the same global permission allowlist in `~/.claude/settings.json`:

```json
"allow": [
  "Bash(git pull*)",
  "Bash(git -C * pull*)",
  "Bash(gh issue list*)",
  "Bash(gh issue create*)",
  "Bash(gh label list*)",
  "Bash(gh label create*)",
  "Bash(gh api*)",
  "Bash(cat *)",
  "Bash(ls *)",
  "Bash(find *)",
  "Bash(echo *)"
]
```

New agents that need additional commands (e.g., `curl` for Slack webhooks, `python3` for the fabricator) must have those commands added to this list.

---

## Debugging an Agent

| Symptom | Check |
|---|---|
| Agent prompt hangs | Command not in allowlist — check `~/.claude/settings.json` |
| Duplicate issues created | Dedup logic in CLAUDE.md — check the title-matching pattern |
| Agent not firing | Cron TTL expired — run `CronList` to verify |
| Wrong severity | Update the severity rubric in `CLAUDE.md` or the relevant `agents/` file |
| Missing correlation | Check `deployed_at` format in `deploys/recent.json` — must be ISO 8601 |
| Compliance violation missed | Check the rule text in `compliance-policy.md` matches the audit check in `agents/compliance-agent.md` |
