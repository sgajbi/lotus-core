# CR-1463: Backdated Cost Suffix Correction

Date: 2026-07-10
Issue: #468
Status: Hardened locally; remaining backdated combinations tracked

## Objective

Prevent a backdated transaction from leaving later canonical transaction cost and realized-P&L
rows stale while preserving one downstream processed event per booked input.

## Defect And Correction

The cost engine recalculated the complete ordered timeline, but the workflow persisted only the
incoming transaction. A cheaper backdated FIFO buy therefore recalculated a later disposal from
`200` to `400` realized gain in memory while the database retained `200`.

The workflow now:

1. recalculates the full normalized portfolio-security timeline;
2. fails closed if any timeline transaction has an engine error;
3. locates the incoming transaction in the engine's deterministic order;
4. persists the incoming transaction and every later recalculated row in that affected suffix;
5. returns and publishes only the incoming transaction event;
6. commits suffix corrections, cost breakdowns, lot state, position rebuild, and outbox work in the
   existing combined unit of work.

Publishing only the incoming event is intentional. The combined position adapter rebuilds the
current epoch from corrected canonical rows; publishing the suffix would apply later positions a
second time and change the established Kafka contract.

## Evidence

- pre-fix PostgreSQL regression: later FIFO disposal incorrectly remained `200`;
- post-fix backdated FIFO: corrected disposal is `400`;
- post-fix backdated AVCO: corrected disposal is `300`;
- injected later-suffix persistence failure: incoming/suffix costs, lot state, epoch, and outbox
  changes all roll back;
- one `ProcessedTransactionPersisted` event remains emitted per booked input;
- full combined PostgreSQL pack: 15 passed in 101.27 seconds;
- focused backdated PostgreSQL pack: 4 passed in 60.48 seconds;
- cost and target unit pack: 231 passed; final touched pack: 106 passed;
- MyPy passed for 35 touched source files; architecture, Ruff, format, and diff gates passed.

## Compatibility And Remaining Work

This intentionally corrects persisted later cost/P&L values for backdated inputs. API, Kafka
topic/group/payload shape, database schema, idempotency identity, and normal event count are
unchanged. Recalculation now fails closed when any historical or later row cannot be recalculated,
instead of committing around an ignored timeline error.

Backdated multi-lot fee and cross-currency combinations remain explicit cutover evidence. The
generic suffix algorithm applies to them, and existing in-order fee, FX, and multi-lot combined
paths remain green, but this CR does not claim those backdated combinations without direct proof.
