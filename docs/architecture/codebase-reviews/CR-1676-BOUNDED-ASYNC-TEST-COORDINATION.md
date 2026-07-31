# CR-1676: Bounded Async Test Coordination

## Scope

This review covers GitHub issue #875 and the same-pattern scan of Core integration tests that use
task-published events to coordinate database concurrency assertions.

## Finding

The derived-state advisory-fence proof waited directly for an event published only after the first
session connected and acquired its fence. A connection or acquisition failure therefore removed
the event's only producer and hid the database exception behind an unbounded wait. The adjacent
position-recalculation concurrency proof used bounded event waits, but it had the same delayed
failure propagation and did not guarantee both tasks were awaited or cancelled on every exit path.

## Correction

`tests.test_support.async_task_coordination` now supervises a producer task and its event together.
It returns on the signal, immediately propagates an early task exception, rejects successful task
completion without the promised signal, and raises a deterministic timeout for a stuck producer.
The companion cleanup helper cancels and awaits unfinished tasks without masking the original test
failure.

Both affected PostgreSQL tests use the helper and release their held lock/fence in `finally`. Each
second session publishes its PostgreSQL backend PID before calling the repository. A bounded
observer then requires `pg_locks` to expose an ungranted advisory lock for that exact backend before
the first transaction is released. The tests subsequently prove acquisition and clean completion.
Observer connection checkout, every query, and cancellation observation share the same remaining
deadline while the contender task remains supervised. Cleanup that ignores cancellation is detached
with its eventual outcome consumed rather than extending the caller's deadline. The shared pending
task cleanup helper applies the same rule under its own explicit bound, so SQLAlchemy/asyncpg
transaction cleanup cannot turn an assertion failure into a job-timeout hang. The adjacent
cost-basis FIFO concurrency proof now uses the same supervised signals, exact-backend `pg_locks`
evidence, and `finally` cleanup for its buy, sell, and replay tasks. These tests no longer infer
serialization from a sleep or from client-side call ordering.

## Same-Pattern Review

The scan covered integration-test `asyncio.Event.wait()` calls, including the cost-basis lock proof
identified during PR review. Other barrier-style tests either
publish their signal before fallible database work or place the complete participant set under one
bounded `gather`/`Barrier`; they do not have the producerless event-wait defect. The two corrected
tests were the in-scope cases where fallible connection or lock work preceded the awaited signal.

## Compatibility And Documentation

This is test-harness reliability only. Production source, APIs, OpenAPI, events, schemas,
migrations, calculations, runtime topology, and downstream contracts are unchanged. The review
ledger and repository context change because the coordination rule is reusable. README and authored
wiki are explicit no-change because no developer command, operator flow, or published capability
changed. Existing platform skills already require bounded waits, failure propagation, cleanup, and
same-pattern review, so central context and skills are also unchanged.

## Validation

- warning-strict task-coordination unit tests: `10 passed`;
- real PostgreSQL derived-state, position-history, and cost-basis concurrency tests: `3 passed`;
- targeted Ruff lint and format: passed;
- targeted configured MyPy: passed;
- architecture documentation, docs/wiki, and diff-hygiene gates: passed.
