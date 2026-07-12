# CR-284 Outbox Flush Timeout Accounting Review

## Finding

`OutboxDispatcher._process_batch_sync()` assumed that a non-exceptional `flush(...)` meant
every queued row would eventually appear in `delivery_ack`. That is not guaranteed:
`KafkaProducer.flush(timeout=...)` can return a positive undelivered count without raising.

Before this fix, rows that were still queued at flush timeout could slip through with:

- no success callback
- no failure callback
- no retry increment
- no terminal-failure accounting

That made the outbox batch outcome incomplete and hid a real producer-timeout path from the
durable retry state.

## Action Taken

- treated `flush(...) > 0` as an explicit failure-accounting path for rows that still had no
  delivery callback
- marked those callback-less rows as failed deliveries for the current batch so the normal retry
  accounting applies
- added a DB-backed integration proof where:
  - one queued row gets a success callback
  - a second queued row gets no callback
  - `flush(...)` returns `1`
  - the first row becomes `PROCESSED`
  - the second row remains `PENDING` with `retry_count = 1`

## Status

Hardened

## Follow-up

- keep auditing producer timeout semantics anywhere queue code treats “no exception” as “fully
  accounted”
- if producer timeouts become a common runtime mode, consider a dedicated metric for callback-less
  flush timeouts

## Evidence

- `src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py`
- `tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py`
- `python -m pytest tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py`
