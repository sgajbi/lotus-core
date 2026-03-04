# RFC 066 - Institutional-Scale Production Readiness and Performance Assurance

## Status
In Progress

## Date
2026-03-04

## Owners
- lotus-core: execution and operational contracts
- lotus-platform: cross-service governance and standards

## 1. Summary
This RFC defines the post-RFC-065 path to make lotus-core institution-ready for unknown production load profiles. The objective is not only correctness, but sustained performance, resilience, and operational predictability under extreme load.

## 2. Problem Statement
Functional correctness alone is insufficient for bank/fintech deployments. We must prevent late-stage architectural rework by enforcing:
1. measurable performance envelopes,
2. deterministic scaling behavior,
3. replay/failure isolation under stress,
4. CI-enforced operational contracts.

## 3. Goals
1. Establish enforceable production SLO/SLA envelopes for high-load scenarios.
2. Validate scaling and replay behavior under steady-state, burst, and replay-storm workloads.
3. Detect regressions pre-merge through deterministic automation.
4. Make runtime operating policy introspectable and drift-resistant.

## 4. Non-Goals
1. Move risk/performance analytics computation into lotus-core.
2. Replace existing calculators with new engines in a single release.
3. Introduce non-canonical terminology or API aliases.

## 5. Target Readiness Model
1. **Performance contracts**: p95/p99 latency, lag age, drain-time, DLQ pressure, replay pressure.
2. **Capacity contracts**: explicit `lambda_in`, `mu_msg`, `rho`, `headroom`, `T_drain` signals.
3. **Policy contracts**: all critical runtime thresholds available via API (`/ingestion/health/policy`).
4. **Operational contracts**: deterministic smoke and latency gates that fail on drift.
5. **Resilience contracts**: replay isolation mode + partition growth strategy must be explicit decisions.

## 6. Delivery Slices

### Slice A - Contract Hardening (Completed in this change set)
1. Extend deterministic docker smoke to validate ingestion ops endpoints:
- `/ingestion/health/operating-band`
- `/ingestion/health/policy`
- `/ingestion/health/reprocessing-queue`
- `/ingestion/health/backlog-breakdown`
- `/ingestion/health/stalled-jobs`
- `/ingestion/health/capacity`
2. Add contract-level checks in smoke output for:
- policy decision fields (`calculator_peak_lag_age_seconds`, `replay_isolation_mode`, `partition_growth_strategy`)
- capacity signal fields (`lambda_in_events_per_second`, `mu_msg_per_replica_events_per_second`, `utilization_ratio`, `headroom_ratio`, `saturation_state`)

### Slice B - Load Profile Gate
1. Add deterministic load profile runner for:
- steady-state
- burst
- replay-storm
2. Add CI gate to assert no SLO regression vs baseline envelope.

### Slice C - Failure Injection and Recovery
1. Add controlled chaos scenarios:
- Kafka slowdown / backlog surge
- worker interruption
- replay collision flood
2. Verify recovery SLO:
- bounded drain time
- no correctness drift
- no runaway DLQ pressure.

### Slice D - Institutional Sign-Off Pack
1. Publish runbooks and quantitative evidence pack.
2. Add explicit go-live checklist for customer onboarding readiness.

## 7. Acceptance Criteria
1. All runtime policy decisions visible via API and covered by tests.
2. Docker smoke verifies both endpoint availability and contract fields.
3. Latency and load gates run in CI with deterministic thresholds.
4. Replay and scaling behavior remain deterministic under stress.
5. No unresolved Sev-1/Sev-2 performance risks for launch.

## 8. Risks and Mitigations
1. **False confidence from light tests**
- Mitigation: enforce heavy-profile gates (Slice B/C) before GA sign-off.
2. **Policy drift across environments**
- Mitigation: fingerprinted policy endpoint + CI drift checks.
3. **Hot-key portfolio skew**
- Mitigation: partition strategy decision is explicit and testable.

## 9. Implementation Notes
RFC-065 remains the foundational scalability roadmap. RFC-066 is the production-readiness enforcement layer that turns those decisions into auditable, CI-gated operating guarantees.

## 10. Progress (2026-03-04)

### Slice A - Completed
1. Deterministic docker smoke expanded to cover ingestion operations and policy/capacity contracts.
2. Contract checks now fail explicitly on missing institutional policy fields or missing capacity signals.

### Slice B - Completed in this change set
1. Added deterministic load profile runner: `scripts/performance_load_gate.py`.
2. Implemented three profiles:
- `steady_state`
- `burst`
- `replay_storm`
3. Added enforceable threshold evaluation with per-profile failure reasons:
- throughput floor
- backlog-age ceiling
- DLQ pressure ceiling
- replay pressure ceiling
- backlog drain-time ceiling
4. Added JSON/Markdown artifact generation:
- `output/task-runs/*performance-load-gate*.json`
- `output/task-runs/*performance-load-gate*.md`
5. Added CI job `Performance Load Gate` in `.github/workflows/ci.yml`.
6. Added make target `test-performance-load-gate` and wired lint/format coverage for the new script.

### Slice B.1 - CI Strategy Hardening (Completed in this change set)
1. Split load testing into two tiers:
- `fast` profile tier for PR gating (quick signal, low runtime, no drain wait enforcement).
- `full` profile tier for institutional verification (includes drain invariants and heavier replay stress).
2. Updated pipeline strategy:
- PR/push path runs `Performance Load Gate (Fast)`.
- Scheduled/manual/main path runs `Performance Load Gate (Full)`.
3. Added explicit make targets:
- `test-performance-load-gate` (fast tier)
- `test-performance-load-gate-full` (full tier)
4. Reduced PR lead time without dropping quality, while preserving heavyweight evidence collection for production readiness.
