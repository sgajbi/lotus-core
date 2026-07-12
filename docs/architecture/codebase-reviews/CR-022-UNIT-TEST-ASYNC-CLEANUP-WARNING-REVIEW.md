# CR-022 Unit-Test Async Cleanup Warning Review

## Scope

Review and eliminate the async cleanup warnings surfaced by the branch-scoped
unit premerge gate.

## Findings

The unit suite was green but still emitted runtime warnings of the form:

- `coroutine method 'aclose' of 'get_async_db_session' was never awaited`

These warnings came from test doubles, not from a newly introduced production
regression:

1. Several unit tests monkeypatched `get_async_db_session` with raw async
   generator functions that yielded exactly one fake session.
2. A Kafka consumer payload-format test exercised `_record_consumer_dlq_event`
   even though the behavior under test was only DLQ payload formatting, not DB
   persistence.

The result was noisy but real test-harness debt. It reduced confidence in the
unit gate because warnings looked like latent async resource leaks.

## Actions Taken

1. Replaced raw async-generator test doubles with explicit single-yield async
   iterators in:
   - `test_valuation_readiness_consumer.py`
   - `test_ingestion_job_service_backlog_breakdown.py`
   - `test_ingestion_job_service_capacity_status.py`
2. Stopped the Kafka payload-format test from hitting the real DB-recording path
   by mocking `_record_consumer_dlq_event` directly in the test.
3. Re-ran the previously warning-producing tests with warnings enabled to prove
   the warnings are gone.

## Result

The warning-producing unit paths are now clean, and the branch-scoped unit gate
no longer carries those false-negative style cleanup warnings from this review
set.

## Follow-up

If more async cleanup warnings appear later, treat them as test-harness defects
first and reproduce them with targeted warning-enabled runs before changing
production code.
