# CR-283 Outbox Synchronous Publish Failure Fence Review

## Finding

`OutboxDispatcher._process_batch_sync()` treated delivery callbacks as the only failure path
inside one batch. If `KafkaProducer.publish_message(...)` raised synchronously for one event
mid-loop, the whole batch aborted before the dispatcher had a chance to flush and account for
rows already queued earlier in the same batch.

That created a real correctness risk:

- earlier rows could already be buffered in the producer
- the database transaction would still roll back
- the batch would remain `PENDING` without an accurate retry/accounting outcome
- a later flush cycle could produce confusing duplicate or ghost delivery behavior

## Action Taken

- fenced synchronous `publish_message(...)` failures per row inside the dispatcher loop
- recorded those rows as failed delivery outcomes instead of aborting the whole batch
- kept the batch moving so previously queued rows still reach `flush(...)` and get durable
  accounting updates
- added a DB-backed integration proof for a mixed batch:
  - row 1 queues successfully
  - row 2 raises synchronously during `publish_message(...)`
  - row 3 queues successfully
  - rows 1 and 3 become `PROCESSED`
  - row 2 remains `PENDING` with `retry_count = 1`

## Status

Hardened

## Follow-up

- keep checking producer-adjacent paths for other failure modes that bypass normal callback-based
  accounting
- if outbox semantics ever become stricter than at-least-once, revisit whether producer-side
  transactions are warranted

## Evidence

- `src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py`
- `tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py`
- `python -m pytest tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py`
