# CR-1482: Kafka Consumer Drain And Replay Controls

Date: 2026-07-10
Issue: #468
Status: Hardened locally; deployed drain evidence pending

## Objective

Make the final replay consumer bounded, ordered, observable, and safe during worker shutdown without
adding Kafka lifecycle policy to the replay delivery or application layers.

## Finding

`BaseConsumer.shutdown()` stopped polling and immediately closed the Kafka consumer. If a live or
replay message was still executing, processing could finish only after the underlying consumer was
closed, so the success offset could not be safely committed. The shared supervisor also used a
fixed 10-second task timeout while consumer execution profiles allowed a 30-second drain window.
That made the configured drain contract ineffective during normal runtime teardown.

The final transaction-processing composition also relied on each consumer constructor to discover
its profile implicitly. The live and replay groups were distinct, but their independent throughput
controls were not visible at the composition boundary.

## Change

- `shutdown()` now performs a two-phase lifecycle: stop polling and wake the loop first, then close
  Kafka and flush the DLQ producer only after the active run loop has drained and exited.
- Poll wake-up exceptions during an intentional stop are treated as loop termination, not critical
  consumer failure.
- Shared runtime supervision derives its default task timeout from the largest configured consumer
  drain window plus one second, while an explicit caller timeout remains authoritative.
- The final transaction-processing composition loads and injects separate execution profiles for
  `portfolio_transaction_processing_group` and
  `portfolio_transaction_replay_request_group`.
- The real replay consumer proves same-partition order, ordered commits, bounded
  `ordering_key_busy` backlog pressure, and active-replay drain before close.

## Compatibility And Runtime Impact

Topics, payloads, consumer groups, retry/DLQ budgets, successful offset semantics, and business
behavior are unchanged. Intentional shutdown now permits already-polled work to complete and commit
before resource release. Unprocessed offsets remain available for Kafka redelivery. The default
runtime teardown bound increases only when a consumer advertises a longer drain window.

The target remains undeployed. The current three-worker runtime topology is unchanged. Operators
may tune live and replay in-flight capacity independently through the existing group override JSON;
per-partition concurrency remains one.

## Validation

- shared Kafka/runtime/worker pack: `77 passed`;
- target replay/composition/application/adapter pack: `25 passed`;
- focused target replay/composition pack: `17 passed`;
- PostgreSQL duplicate replay semantic parity: `1 passed in 55.34 seconds`;
- repository MyPy scope: `51 source files`, no issues;
- full Ruff lint and format gates passed;
- strict architecture and observability contract gates passed;
- architecture catalog, wiki/docs, front-door, and diff gates passed.

Deployed restart duration, Kafka lag recovery, and p50/p95/p99 processing evidence remain part of
the atomic cutover gate.
