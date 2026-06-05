# Always-On Ops Agent — Plan

## Context
An always-on agent that monitors this repo without needing to be manually started. It uses Claude Code's durable cron to schedule a recurring prompt that analyzes incidents, deployments, and vendor contracts, then opens GitHub Issues for every finding. Runs every 4 hours and survives Claude Code restarts (auto-expires after 7 days).

## Architecture: Two Layers

1. **`CLAUDE.md`** in this repo — the agent's brain. Contains all analysis rules, output formats, and deduplication logic. Versioned in git.
2. **Durable cron prompt** — a short prompt that says "cd to repo, git pull, follow the CLAUDE.md protocol." Keeps the cron lightweight.

## What the Agent Does Each Run

### Task 1: Ops Triage
- Reads each file in `issues/`
- Assigns P0–P3 severity based on customer impact and urgency
- Matches issues to runbooks in `runbooks/`
- Recommends specific fix steps and which on-call team to page
- Opens a `[Agent Triage]` GitHub Issue for each production incident

### Task 2: Incident Correlation
- Reads `deploys/recent.json`
- Cross-references each issue with deploys that happened within 48 hours before the incident
- Identifies root causes and causal chains (e.g., a feature flag + a deploy together triggering a bug)
- Recommends rollbacks where available
- Opens a `[Agent Correlation]` GitHub Issue for each confirmed correlation

### Task 3: Compliance Audit
- Reads `compliance-policy.md` (7 rules)
- Audits each vendor contract in `contracts/`
- Flags specific violations with the exact contract clause and policy gap
- Opens a `[Agent Compliance]` GitHub Issue per violation

### Deduplication
Before creating any issue, the agent checks `gh issue list --label ops-agent` and skips anything already reported. Re-runs only surface new findings.

## Expected First-Run Output (~14 GitHub Issues)

| Type | Issue | Finding |
|---|---|---|
| Triage | PROD-4521 | P0 — PaymentService NPE, 340% error rate spike |
| Triage | PROD-4487 | P1 — Acme Corp checkout broken, 2,400 users affected |
| Triage | PROD-4498 | P2 — Intermittent login 502s, connection pool exhaustion |
| Triage | PROD-4519 | P2 — Slow image uploads, CDN/signing-service issue |
| Triage | PROD-4506 | P3 — Feature request: parallel batch jobs |
| Correlation | PROD-4521 | Caused by `payment-service v4.8.2` (deployed 14 min before incident) — rollback recommended |
| Correlation | PROD-4487 | Caused by `tenant-config-service v3.2.1` + `payment-service v4.8.2` (causal chain) |
| Correlation | PROD-4519 | Caused by `signing-service v2.1.4` (URL TTL reduced from 3600s to 300s) |
| Correlation | PROD-4498 | Linked to `auth-service v6.0.0` (Redis session storage migration) |
| Compliance | Sirius Storage | 5–6 violations: data residency, audit rights, termination, liability cap, subprocessors, breach notification |
| Compliance | Acme Data Platform | 3 violations: data residency, subprocessor notice timing, breach notification (96h vs 72h) |
| Compliance | Globex Messaging | Fully compliant — no issue opened |

## Implementation

### Files Created
- `CLAUDE.md` — full agent protocol (this repo)
- `.claude/settings.json` — non-interactive permissions for cron runs (this repo)

### GitHub Setup
- Issues enabled on `ruscoe888/always-on-agent`
- Labels created: `ops-agent`, `agent-triage`, `agent-correlation`, `agent-compliance`

### Cron Schedule
- **Frequency:** Every 4 hours at :17 past the hour
- **Durable:** Survives Claude Code restarts
- **Auto-expires:** 7 days from creation

## Re-Creating the Cron After 7 Days

The cron auto-expires after 7 days. To restart it, run this in Claude Code:

```
Create a durable recurring cron job with:
- cron: "17 */4 * * *"
- durable: true
- recurring: true
- prompt: "You are the always-on ops agent. Execute the following steps: 1. Run: git -C /Users/pruscoe/Claude/hackathon pull origin main 2. Read the CLAUDE.md file at /Users/pruscoe/Claude/hackathon/CLAUDE.md — it contains your full operating protocol under 'Ops Agent Run Protocol'. 3. Execute all three tasks (Ops Triage, Incident Correlation, Compliance Audit). 4. Follow the deduplication rules. 5. Print the run summary when done."
```

## Proving It Works

To trigger the agent immediately (rather than waiting for the next scheduled run), say:
> "Run the ops agent protocol now"

Claude Code will execute the full protocol live — you can watch it create GitHub Issues in real time at `github.com/ruscoe888/always-on-agent/issues`.
