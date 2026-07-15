# Portfolio Derived-State Poison-Message Recovery

## Purpose

Use this procedure to certify that malformed valuation snapshot events are contained without
blocking later valid portfolio derived-state work or corrupting position and portfolio timeseries.

The shared Kafka consumer boundary owns the terminal sequence:

1. classify the raised adapter failure,
2. publish and confirm the DLQ record,
3. persist source-safe consumer-DLQ support evidence,
4. commit the exact source offset only after steps 2 and 3 succeed.

Service delivery adapters must not publish directly to DLQ or commit terminal source offsets.

## Command

```bash
make test-derived-state-poison-gate
```

The target starts an isolated managed Compose project and builds the required image set unless
`LOTUS_RUNTIME_IMAGE_SET_VERIFIED=true` truthfully identifies an already verified image set.

For diagnosis against an explicitly managed stack, provide `--skip-compose` and all generated
endpoint and Kafka/database arguments directly to the module. Do not point it at a shared or
production runtime.

## Scenario

The gate:

1. waits for ingestion, event-replay support, and derived-state readiness,
2. seeds one isolated portfolio, instruments, and same-currency prices,
3. records source-consumer lag and the DLQ topic high watermark,
4. publishes one uniquely keyed malformed `valuation.snapshot.persisted` event,
5. waits for its exact correlation/key evidence on the governed consumer-DLQ support API,
6. submits one valid booked transaction through ingestion,
7. waits for the valid snapshot, position timeseries, and portfolio timeseries outputs,
8. verifies both durable queues are closed and source lag returned to baseline,
9. requires the DLQ topic to have grown by exactly one record,
10. requires exactly one matching support event with `VALIDATION_ERROR`,
11. runs timeseries-integrity reconciliation and requires zero findings.

## Evidence

The gate writes:

- `output/task-runs/<run-id>-derived-state-poison-gate.json`
- `output/task-runs/<run-id>-derived-state-poison-gate.md`
- `output/task-runs/diagnostics/derived-state-poison-gate-compose.log`

The JSON artifact is the machine-readable result. A source commit, unit test, or static guard is not
a substitute for a passing managed artifact.

## Failure Handling

If the poison message is not visible in support evidence, inspect the exact managed project logs,
DLQ topic permissions, producer delivery confirmation, database connectivity, and
`consumer_dlq_events` persistence. Do not manually advance the source consumer offset.

If a later valid message does not progress, inspect source lag, valuation and aggregation job
status, lease ownership, outbox status, and reconciliation findings before replay. Use the governed
event-replay path only after correcting the source or consumer defect.

If DLQ publication or support-evidence persistence fails, the expected posture is no source commit.
Restore the dependency and allow Kafka redelivery; a configured bounded failure budget may stop the
consumer but must not acknowledge the poison source message.
