#!/usr/bin/env python3
"""
Issue Fabricator — randomly generates a realistic synthetic PROD issue,
commits it to the repo, and pushes. Designed to be called by a cron or
run manually to keep the live feed active.

Usage:
  python3 scripts/fabricate-issue.py
"""

import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISSUES_DIR = os.path.join(REPO_ROOT, "issues")

# ── Issue templates ───────────────────────────────────────────────────────────

SERVICES = [
    "auth-service", "payment-service", "reporting-service",
    "notification-service", "search-indexer", "export-worker",
    "api-gateway", "signing-service", "tenant-config-service",
    "webhook-service", "billing-service", "audit-service",
]

CUSTOMERS = [
    "Acme Corp", "Initech", "Globex Corp", "Umbrella Ltd",
    "Vandelay Industries", "Cyberdyne Systems", "Massive Dynamic",
    "Buy N Large", "Soylent Corp", "Bluth Company",
]

REPORTERS = [
    "monitoring-alerts@bts-synthetic.example",
    "customer-support@bts-synthetic.example",
    "customer-success@bts-synthetic.example",
    "oncall@bts-synthetic.example",
    "platform-alerts@bts-synthetic.example",
]

TEMPLATES = [
    {
        "title_tpl": "{service} memory usage at {pct}% — OOMKill risk on {env}",
        "labels": ["infrastructure", "performance"],
        "body_tpl": (
            "Memory alert fired at {time} UTC. {service} pods on {env} are consuming {pct}% of their "
            "allocated {mem}GB limit. Pod restarts will begin automatically if usage exceeds the limit. "
            "Heap dump analysis shows {cause}. "
            "{count} customer-facing requests have already experienced elevated latency (p99 {lat}ms vs normal {norm}ms). "
            "Affected customers include {customer1} and {customer2}. "
            "No recent deploys to this service in the last 72 hours — suspected slow memory leak or unexpected traffic spike."
        ),
        "vars": lambda: {
            "pct": random.randint(82, 96),
            "mem": random.choice([2, 4, 8]),
            "env": random.choice(["us-east-1", "eu-west-2", "ap-southeast-1"]),
            "cause": random.choice([
                "large object retention in the session cache",
                "unbounded growth in the request deduplication map",
                "unclosed database connections holding result sets",
            ]),
            "count": random.randint(200, 4000),
            "lat": random.randint(1800, 6000),
            "norm": random.randint(120, 400),
            "customer1": random.choice(CUSTOMERS),
            "customer2": random.choice(CUSTOMERS),
        },
    },
    {
        "title_tpl": "Intermittent 503s on {endpoint} — error rate {pct}% over last {mins} minutes",
        "labels": ["customer-impact", "api"],
        "body_tpl": (
            "Synthetic monitoring triggered at {time} UTC. {endpoint} is returning HTTP 503 errors in "
            "bursts lasting {burst}s. Error rate over the last {mins} minutes is {pct}%. "
            "Load balancer logs show upstream connection refused from {n} of {total} backend pods. "
            "The affected pods are not restarting — they appear alive to the health check but rejecting connections. "
            "Pattern matches connection pool exhaustion or thread pool saturation. "
            "{customer1} support has already opened a ticket. Estimated {users} users affected."
        ),
        "vars": lambda: {
            "endpoint": random.choice([
                "POST /v2/orders", "GET /v2/inventory",
                "PUT /v2/products", "POST /v2/checkout",
                "GET /v2/reports", "POST /v2/webhooks/ingest",
            ]),
            "pct": round(random.uniform(8, 35), 1),
            "mins": random.choice([10, 15, 20, 30]),
            "burst": random.randint(15, 60),
            "n": random.randint(2, 5),
            "total": random.randint(6, 12),
            "customer1": random.choice(CUSTOMERS),
            "users": random.randint(300, 8000),
        },
    },
    {
        "title_tpl": "Database replication lag on {db} — {lag}s behind primary",
        "labels": ["data", "infrastructure"],
        "body_tpl": (
            "Replication lag alert at {time} UTC. The {db} read replica is {lag} seconds behind the primary "
            "(normal: <{norm}s). Read traffic routed to the replica is receiving stale data. "
            "Affected read paths: {paths}. "
            "Primary write load has increased {pct}% in the last hour — suspected cause is a large batch job "
            "or unoptimised bulk update creating excessive WAL volume. "
            "If lag exceeds {threshold}s the read replica will be taken offline automatically, routing all traffic "
            "to the primary — this will increase primary load significantly. "
            "Customers on the reporting dashboard ({customer1}, {customer2}) are seeing data that is {lag} seconds old."
        ),
        "vars": lambda: {
            "db": random.choice(["users-db", "analytics-db", "billing-db", "orders-db", "audit-db"]),
            "lag": random.randint(45, 300),
            "norm": random.randint(2, 5),
            "paths": random.choice([
                "/reports/*, /dashboard/*, /exports/*",
                "/v2/inventory, /v2/products",
                "/auth/sessions, /user/profile",
            ]),
            "pct": random.randint(30, 180),
            "threshold": random.choice([300, 600, 900]),
            "customer1": random.choice(CUSTOMERS),
            "customer2": random.choice(CUSTOMERS),
        },
    },
    {
        "title_tpl": "TLS certificate expiring in {days} days — {domain}",
        "labels": ["security", "infrastructure"],
        "body_tpl": (
            "Certificate expiry alert at {time} UTC. The TLS certificate for {domain} expires in {days} days "
            "({expiry}). Auto-renewal has failed {attempts} consecutive times with error: '{error}'. "
            "If not renewed, customers will begin seeing browser certificate warnings from {warn_date}. "
            "Enterprise customers with certificate pinning ({customer1}) will experience complete service disruption. "
            "Manual intervention required — auto-renewal is blocked by {blocker}."
        ),
        "vars": lambda: {
            "days": random.randint(3, 14),
            "domain": random.choice([
                "api.bts-synthetic.example",
                "uploads.bts-synthetic.example",
                "auth.bts-synthetic.example",
                "reports.bts-synthetic.example",
            ]),
            "expiry": "2026-06-" + str(random.randint(10, 28)),
            "attempts": random.randint(3, 8),
            "error": random.choice([
                "ACME challenge failed: DNS record not found",
                "Rate limit exceeded: too many certificate requests",
                "IAM permission denied: cannot write to S3 challenge bucket",
            ]),
            "warn_date": "2026-06-" + str(random.randint(8, 20)),
            "customer1": random.choice(CUSTOMERS),
            "blocker": random.choice([
                "a DNS propagation issue introduced in the last infrastructure change",
                "an expired IAM role used by the cert-manager service account",
                "a misconfigured CNAME record following last month's CDN migration",
            ]),
        },
    },
    {
        "title_tpl": "Scheduled job '{job}' has not run in {hours}h — missed {count} executions",
        "labels": ["data", "reliability"],
        "body_tpl": (
            "Job scheduler alert at {time} UTC. The '{job}' job, which normally runs every {interval}, "
            "has not executed in {hours} hours. {count} scheduled executions have been missed. "
            "Downstream impact: {impact}. "
            "The job worker is alive and processing other jobs normally — this appears to be an issue "
            "with the job's trigger record in the scheduler database, possibly caused by a {cause}. "
            "Last successful run: {last_run}. Affected customers: {customer1} and {customer2} "
            "who rely on this job for their {use_case}."
        ),
        "vars": lambda: {
            "job": random.choice([
                "nightly-invoice-generation",
                "daily-compliance-report",
                "hourly-usage-aggregation",
                "5min-cache-warming",
                "weekly-data-retention-sweep",
                "realtime-fraud-scoring",
            ]),
            "interval": random.choice(["5 minutes", "1 hour", "24 hours"]),
            "hours": random.randint(2, 48),
            "count": random.randint(3, 200),
            "impact": random.choice([
                "invoice emails are not being sent to customers",
                "usage dashboards are showing stale metrics",
                "fraud detection is running on cached scores only",
                "old data is not being purged, increasing storage costs",
            ]),
            "cause": random.choice([
                "failed transaction that left a lock on the scheduler row",
                "schema migration that dropped the job's status index",
                "config change that altered the job's cron expression format",
            ]),
            "last_run": f"2026-06-04T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00Z",
            "customer1": random.choice(CUSTOMERS),
            "customer2": random.choice(CUSTOMERS),
            "use_case": random.choice([
                "monthly billing reconciliation",
                "daily SLA reporting",
                "automated compliance audit trail",
            ]),
        },
    },
    {
        "title_tpl": "Elevated 401 errors on API — suspected credential rotation issue",
        "labels": ["security", "api", "customer-impact"],
        "body_tpl": (
            "Authentication error spike at {time} UTC. API 401 Unauthorized responses have increased "
            "{pct}% above baseline over the last {mins} minutes. "
            "Error breakdown: {breakdown}. "
            "Pattern suggests a subset of API keys or service account tokens have been invalidated. "
            "The timing correlates with a scheduled credential rotation that ran at {rotation_time} UTC. "
            "Affected customers ({customer1}, {customer2}, {customer3}) are reporting that their integrations "
            "have stopped working. The rotation script may have invalidated active tokens before issuing replacements, "
            "or the token propagation to the auth-service cache has not yet completed."
        ),
        "vars": lambda: {
            "pct": random.randint(200, 800),
            "mins": random.randint(8, 25),
            "breakdown": random.choice([
                "62% expired tokens, 31% invalid signatures, 7% revoked keys",
                "88% service account tokens, 12% user API keys",
                "100% from customers in the EU-West region",
            ]),
            "rotation_time": f"{random.randint(0,23):02d}:{random.randint(0,59):02d}",
            "customer1": random.choice(CUSTOMERS),
            "customer2": random.choice(CUSTOMERS),
            "customer3": random.choice(CUSTOMERS),
        },
    },
]


def next_prod_id():
    """Find the highest existing PROD-XXXX and increment."""
    existing = []
    for f in os.listdir(ISSUES_DIR):
        if f.startswith("PROD-") and f.endswith(".json"):
            try:
                existing.append(int(f.replace("PROD-", "").replace(".json", "")))
            except ValueError:
                pass
    base = max(existing) if existing else 4500
    # Add a random gap (1-8) so IDs look organic, not sequential
    return base + random.randint(1, 8)


def fabricate():
    template = random.choice(TEMPLATES)
    service  = random.choice(SERVICES)
    reporter = random.choice(REPORTERS)
    prod_id  = next_prod_id()
    now      = datetime.now(timezone.utc)
    time_str = now.strftime("%H:%M")

    vars_fn = template["vars"]
    v = vars_fn()
    v["service"] = service
    v["time"]    = time_str

    title = template["title_tpl"].format(**v)
    body  = template["body_tpl"].format(**v)

    issue = {
        "id":        f"PROD-{prod_id}",
        "title":     title,
        "status":    "open",
        "severity":  None,
        "labels":    template["labels"],
        "assignee":  None,
        "opened_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reporter":  reporter,
        "body":      body,
        "comments":  [],
    }

    filename = os.path.join(ISSUES_DIR, f"PROD-{prod_id}.json")
    with open(filename, "w") as f:
        json.dump(issue, f, indent=2)
        f.write("\n")

    print(f"Created: PROD-{prod_id} — {title[:60]}...")
    return prod_id, filename


def git_push(prod_id, filename):
    rel = os.path.relpath(filename, REPO_ROOT)
    cmds = [
        ["git", "-C", REPO_ROOT, "add", rel],
        ["git", "-C", REPO_ROOT, "commit", "-m",
         f"[fabricator] Add PROD-{prod_id}: auto-generated issue"],
        ["git", "-C", REPO_ROOT, "push", "origin", "main"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
        print(result.stdout.strip() or f"OK: {cmd[3] if len(cmd) > 3 else cmd[-1]}")


if __name__ == "__main__":
    prod_id, filename = fabricate()
    git_push(prod_id, filename)
    print(f"\nDone. PROD-{prod_id} is live in the repo.")
