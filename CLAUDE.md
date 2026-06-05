# Always-On Ops Agent

This is a synthetic enterprise repository used as the working environment for an always-on ops agent. The agent monitors incidents, deployments, and vendor contracts, and opens GitHub Issues for every finding.

**Repo:** `ruscoe888/always-on-agent`
**Agent labels:** `ops-agent` (umbrella), `agent-triage`, `agent-correlation`, `agent-compliance`

---

## Ops Agent Run Protocol

When triggered by the scheduled cron, execute the following three tasks in order. Read all relevant files fresh from disk each run.

---

### Task 1: Ops Triage

For each JSON file in `issues/`:

1. Read the issue (id, title, body, opened_at, labels).
2. Assign a severity using this rubric:
   - **P0** — Active outage, revenue impact, or multiple enterprise customers affected. Requires immediate action.
   - **P1** — Single enterprise customer affected, or significant service degradation. Requires action within 1 hour.
   - **P2** — Intermittent issue, workaround available, or limited user impact. Requires action within 24 hours.
   - **P3** — Feature request, non-urgent, or cosmetic. No urgency.
3. Check for a matching runbook in `runbooks/`:
   - `auth-502-windows.md` → keywords: 502, login, auth, connection pool
   - `cdn-upload-latency.md` → keywords: upload, CDN, slow, latency, image, signing
   - `payment-service-degraded.md` → keywords: PaymentService, checkout, payment, NullPointerException, NPE
4. If a runbook matches, include the recommended fix from it.
5. Suggest an on-call team based on service area:
   - Payment/checkout → `#payments-oncall`
   - Auth/login → `#platform-oncall`
   - Upload/CDN/storage → `#infra-oncall`
   - Feature requests → `#product`

**Create a GitHub Issue for each production incident (not feature requests at P3 unless they are actionable):**

Title: `[Agent Triage] PROD-XXXX: <one-line summary> (PX)`
Labels: `ops-agent`, `agent-triage`
Body must include:
- **Severity:** P0/P1/P2/P3 and rationale
- **Runbook:** Link to runbook file if matched, or "No matching runbook found"
- **Recommended action:** Specific steps drawn from the runbook
- **Escalation:** Which team to page
- **Source:** `issues/PROD-XXXX.json`

---

### Task 2: Incident Correlation

Read `deploys/recent.json` (the `deploys` array). For each production incident in `issues/`:

1. Find deploys that occurred within **48 hours before** the issue's `opened_at` timestamp.
2. Match by service area:
   - Payment/checkout/NPE issues → `payment-service` deploys
   - Auth/login/502 issues → `auth-service` deploys
   - Upload/CDN/image issues → `signing-service` deploys
   - Tenant-specific issues → `tenant-config-service` deploys
3. If a correlation is found:
   - Flag the deploy (service, version, commit SHA, summary, deployed_by).
   - If `rollback_available: true`, explicitly recommend rollback to `last_known_good`.
   - Look for **causal chains**: multiple deploys that together triggered an issue (e.g., a feature flag enabled on top of a new deploy that introduced a bug).
4. Feature requests (P3) do not need correlation analysis.

**Create a GitHub Issue for each confirmed correlation:**

Title: `[Agent Correlation] PROD-XXXX linked to <service> <version>`
Labels: `ops-agent`, `agent-correlation`
Body must include:
- **Issue:** PROD-XXXX title
- **Correlated deploy:** service, version, deployed_at, deployed_by, commit, summary
- **Evidence:** Why this deploy is the likely cause (timing, files changed, feature match)
- **Rollback:** "Rollback available to `vX.X.X` — RECOMMENDED" or "No rollback available"
- **Causal chain:** If multiple deploys are involved, list all and explain the chain
- **Source:** `issues/PROD-XXXX.json`, `deploys/recent.json`

---

### Task 3: Compliance Audit

Read `compliance-policy.md` for the 7 rules. For each contract in `contracts/`:

1. Check every rule:
   1. **Data residency** — EU data must stay in EU. Flag if contract allows processing outside EU or is silent.
   2. **Audit rights** — Must allow audits on ≤30 days' notice, at least once per year. Flag if >90 days' notice required or frequency is too low.
   3. **Termination** — Must allow termination for convenience with ≤90 days' notice. Flag if >90 days or no convenience termination.
   4. **Liability cap** — Must be ≥12 months of fees and must not exclude data breach scenarios. Flag if below 12 months or breach is excluded.
   5. **Subprocessors** — Must provide ≥30 days' written notice **before** engaging a new subprocessor. Flag if no notice, <30 days, or notice is after the fact.
   6. **Breach notification** — Must notify within 72 hours. Flag if >72 hours or no specific window stated.
   7. **Governing law** — Must be in a jurisdiction with mature data protection law (England & Wales, Ireland, EU member state, US Delaware, or equivalent). Flag if not.

2. For each violation, note:
   - The specific contract clause (quote the relevant text).
   - The specific policy rule violated.
   - Severity: **CRITICAL** (data residency, breach notification), **HIGH** (audit rights, termination, liability cap), **MEDIUM** (subprocessors, governing law).

3. If a contract is fully compliant, do **not** open an issue for it.

**Create one GitHub Issue per violation (not per contract):**

Title: `[Agent Compliance] <Contract Name>: <rule violated>`
Labels: `ops-agent`, `agent-compliance`
Body must include:
- **Contract:** Filename and vendor name
- **Rule violated:** Which of the 7 policy rules
- **Severity:** CRITICAL / HIGH / MEDIUM
- **Contract text:** The exact clause causing the violation (quoted)
- **Policy requirement:** What the policy requires
- **Gap:** The specific difference
- **Source:** `contracts/<filename>.md`, `compliance-policy.md`

---

### Deduplication (ALWAYS do this before creating any issue)

Before creating **any** GitHub Issue, run:

```
gh issue list --repo ruscoe888/always-on-agent --label ops-agent --state all --limit 200
```

Parse the output. Apply these dedup rules:
- **Triage/Correlation:** If an issue title already contains the same PROD-XXXX ID and the same type tag (`[Agent Triage]` or `[Agent Correlation]`), skip it and print: `SKIPPED: <title> (already reported)`
- **Compliance:** If an issue title already contains the same contract name and the same rule keyword, skip it.

Create only net-new findings.

---

### Run Summary

After all three tasks, print:

```
=== Ops Agent Run Complete ===
Triage: X issues created, Y skipped (duplicate)
Correlation: X issues created, Y skipped (duplicate)
Compliance: X issues created, Y skipped (duplicate)
Total GitHub issues created this run: N
```

---

## Re-Creating the Cron (7-Day Expiry)

The durable cron auto-expires after 7 days. To re-schedule it, run this prompt in Claude Code:

```
Create a durable recurring cron job with:
- cron: "17 */4 * * *"
- durable: true
- recurring: true
- prompt: "You are the always-on ops agent. Execute the following steps: 1. Run: git -C /Users/pruscoe/Claude/hackathon pull origin main 2. Read the CLAUDE.md file at /Users/pruscoe/Claude/hackathon/CLAUDE.md — it contains your full operating protocol under 'Ops Agent Run Protocol'. 3. Execute all three tasks (Ops Triage, Incident Correlation, Compliance Audit). 4. Follow the deduplication rules. 5. Print the run summary when done."
```
