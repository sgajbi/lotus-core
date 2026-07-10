# CR-1456: Inline Backdated Position Epoch Rebuild

Date: 2026-07-10
Issue: #468
Status: Hardened locally

## Objective

Remove the combined runtime's hidden dependency on legacy `transactions.cost.processed` replay
consumers when a backdated transaction advances position epoch state.

## Defect

The target position adapter reused the deployed `PositionCalculator.calculate()` behavior without
changing its replay policy. A backdated transaction therefore:

1. advanced the position epoch;
2. emitted `ReprocessTransactionReplay` outbox events to `transactions.cost.processed`;
3. returned `replay_queued_count=1` without rebuilding current-epoch position history.

That is valid for the deployed compatibility topology, where dedicated replay consumers subscribe
to the topic. It is invalid for the final two-consumer topology, which intentionally has only the
normal `transactions.persisted` consumer and the operator replay-request consumer. Activating the
target unchanged would strand internal replay events and leave the new epoch incomplete.

## Change

Added explicit `BackdatedPositionHandling` policy:

- `QUEUE_REPLAY` remains the default for deployed legacy consumers;
- `REBUILD_INLINE` is selected by `CombinedPositionCalculationWorkflow` in the target adapter.

For inline handling, the caller-owned transaction now:

1. evaluates the existing deterministic backdated policy;
2. advances epoch state under the existing compare-and-set fence;
3. loads and orders canonical transaction history;
4. tags the rebuild with the new epoch;
5. acquires the existing transaction-scoped position-history lock;
6. rebuilds and persists new-epoch history from the earliest transaction;
7. rearms downstream valuation/timeseries watermarks;
8. commits with cost, cashflow, idempotency, and outbox effects in the same combined unit of work.

No `ReprocessTransactionReplay` event is emitted by the combined path. The shared epoch-advance
logic keeps metrics and stale-winner behavior aligned across both handling modes.

## Complexity And Performance

The target removes an asynchronous queue/reconsume cycle, one compatibility topic dependency, and
eventual-consistency window for backdated position state. Rebuild cost remains proportional to the
affected portfolio/security history, matching the existing correctness-first replay algorithm.
Query count and long-history capacity still require the governed load slice before cutover.

## Compatibility

Deployed legacy behavior is unchanged because `QUEUE_REPLAY` remains the public default. The target
behavior is an intentional internal correction before activation. No public API, event payload,
database schema, active group, image, or deployment manifest changed.

The position wiki and operator troubleshooting guide now distinguish deployed queue replay from
target inline rebuild. Final current-runtime wording will change only during cutover.

## Validation

- PostgreSQL later-BUY then earlier-BUY combined scenario: 1 passed in 49.57 seconds;
- proved epoch `1`, ordered current-epoch quantities `5` then `15`, cost basis `400` then `1400`,
  `replay_queued_count=0`, and zero `ReprocessTransactionReplay` outbox events;
- legacy and target position unit pack: 52 passed;
- combined position plus target unit pack: 109 passed;
- focused MyPy, Ruff, structured-log, in-process boundary, and diff gates passed.
