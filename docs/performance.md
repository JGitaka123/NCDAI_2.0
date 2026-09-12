# Concurrency and performance rehearsal

The bounded rehearsal in [the script](../scripts/performance_check.py) exercises a real local PostgreSQL database through the application's ASGI interface. It does not call the shared development service, start a network listener, use real patient data or contact an AI provider. Each execution creates a unique synthetic facility and preserves its records for inspection. The runner refuses any database other than the dedicated `127.0.0.1:15432/ncdai2_test` target described in ignored runtime configuration.

**Observed result, 12 September 2026 at 17:44 UTC: all four checks passed** on PostgreSQL 18.4 with migration `20260912_guards`. Read latency was p50 **75.48 ms**, p95 **103.76 ms** across 40 successful requests. Registration latency was p50 **102.81 ms**, p95 **222.93 ms** across 32 successful writes. The race produced exactly one successful update and three conflicts. All 37 facility audit events verified after concurrent writes and under every tested database timezone. These are local engineering measurements, not hosted service performance.

The [machine-readable report](test-results/performance-check.json) is the authority for execution status, server/migration version, timeout settings, measured times and passed assertions. A script being present is not evidence that its checks passed. Failed runs record the failing stage and sanitized error class; no password, connection URL or record payload is included. The final report is written when execution ends, so an interrupted process cannot establish a completed result.

The workload is intentionally modest:

| Scenario | Requests | Concurrency | Assertion |
|---|---:|---:|---|
| Dashboard, patient list, encounter and readiness reads | 40 | 4 workers | Every response succeeds. |
| Distinct synthetic patient registrations | 32 | 4 workers | Every response is created; exactly 32 audit events are added with an intact facility chain. |
| Same encounter and expected-version update race | 4 | Barrier-released competitors | Exactly one update succeeds and three return 409; saved version and content match the winner, and only one audit event is added. |
| Audit verification under four database timezones | Four full-chain checks | Sequential | Hashes remain valid in UTC, Nairobi, New York and Kolkata. |

The PostgreSQL application engine is limited to two pooled connections, zero overflow and a five-second pool wait. This makes the four-worker workload include connection sharing. The last two rows check consistency and timezone canonicalization; they do not measure clinical quality.

Latency uses elapsed client time for each request and nearest-rank p50/p95, with maximum and status counts. Timing includes local ASGI, thread scheduling and database work, but excludes public internet, browser rendering, Vercel routing, deployment cold starts and external provider calls. Login, setup and timezone checks are outside the latency sample. Small samples on a shared workstation are unsuitable for national capacity estimates, hosted SLO assertions or comparisons with commercial products. Repeat under a specified deployment/load profile before sizing infrastructure.

From the repository root, after preparing and migrating the isolated test service:

```powershell
.\backend\.venv\Scripts\python.exe scripts\performance_check.py
```

The script adds records and never deletes, restores or restarts a database. Inspect the report's timestamp and `run_status` before using its numbers. The separate database recovery harness covers backup/restore and restart persistence; this rehearsal does not establish those controls or a recovery objective.
