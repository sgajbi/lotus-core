# Portfolio Derived-State Interruption Recovery

## Purpose

Prove that `portfolio_derived_state_service` can recover from a bounded process interruption
without losing, duplicating, or partially publishing portfolio derived state. The gate exercises
the combined deployable while preserving separate position-timeseries and portfolio-timeseries
application/domain ownership.

## Recovery Boundary

The source boundary is the committed `valuation.snapshot.persisted` topic. The preserved
`timeseries_generator_group_positions` consumer group advances only after position-timeseries work
commits. Position materialization stages `portfolio_aggregation_jobs` in the same database
transaction; bounded aggregation workers recover and drain those durable jobs after the runtime
resumes.

The gate does not restore the retired private aggregation Kafka command, split deployables, or
split health surfaces.

## Run

Docker Desktop or an equivalent Docker Engine must be running. The command creates an isolated
Compose project with dynamically reserved host ports and removes it after the run:

```powershell
make test-derived-state-recovery-gate
```

Use the module directly only when explicit local endpoint or timeout overrides are required:

```powershell
python -m scripts.operations.recovery.derived_state_gate --build --enforce
```

CI loads the exact Git-SHA image set before calling the Make target, so the target omits `--build`
when `LOTUS_RUNTIME_IMAGE_SET_VERIFIED=true`.

## Enforced Invariants

For one run-scoped portfolio and business date, the gate:

1. records baseline DLQ count and committed source-topic lag;
2. pauses the exact `portfolio_derived_state_service` Compose container;
3. ingests one BUY for each unique seeded security while upstream transaction processing and
   valuation remain active;
4. proves the expected `daily_position_snapshots` rows materialize during the interruption;
5. proves committed consumer lag grows by at least the expected position count;
6. resumes the same container and requires exact position-timeseries and portfolio-timeseries
   output counts;
7. requires valuation and aggregation queues to contain no `PENDING` or `PROCESSING` work;
8. requires source-topic lag to return to or below the recorded baseline within the recovery
   budget;
9. runs timeseries-integrity reconciliation and requires zero findings; and
10. requires no additional DLQ events during recovery.

Any unmet invariant is listed under `failed_checks`; `--enforce` returns a non-zero exit code.

## Evidence

Each run writes:

- `output/task-runs/<run-id>-derived-state-recovery-gate.json`
- `output/task-runs/<run-id>-derived-state-recovery-gate.md`
- `output/task-runs/diagnostics/derived-state-recovery-gate-compose.log`

The JSON report records the exact container ID, interruption duration, baseline/peak/recovered lag,
source materialization time, recovery time, durable counts, reconciliation findings, DLQ delta,
and failed checks. PR and main releasability workflows upload the same artifacts.

## Failure Handling

Do not raise the timeout to conceal a failure. Preserve the JSON, Markdown, and Compose diagnostic
artifacts; inspect consumer lag, owned queue states, service readiness, and reconciliation findings.
Fix the responsible application, domain, port, or adapter boundary and rerun the same command.

## Compatibility Decision

The gate changes no public API, OpenAPI schema, event payload, database schema, consumer-group
identity, query response, or downstream contract. It certifies the existing unified runtime and
its durable recovery semantics.
