# CR-1445: Combined Integration Test Structure

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Keep combined transaction-processing proof easy to extend and navigate without hiding financial
behavior behind opaque fixtures.

## Change

Added `tests/test_support/transaction_processing.py` with domain-named helpers for:

- portfolio and instrument records;
- booked transaction events and canonical transaction records;
- the concrete combined use-case test context;
- canonical transaction persistence before `transactions.persisted` processing;
- processing an already-booked event for duplicate/replay assertions.

Split the 496-line mixed transaction variant module into independently discoverable modules:

- baseline FIFO BUY/SELL: 160 lines;
- fee-aware full disposal: 179 lines;
- effective-dated FX: 148 lines;
- adjustment: 134 lines.

Scenario inputs, financial expectations, and database assertions remain local to each test module.
Only stable setup ownership moved to shared support.

## Compatibility

No production source, runtime topology, event contract, schema, calculation policy, or persistence
behavior changed. The same eight combined integration paths remain collected.

## Validation

- focused support-module MyPy passed;
- focused Ruff format and lint passed;
- support-module import proof passed;
- all eight target integration tests collected under their expected domain-specific modules;
- full PostgreSQL target pack is the commit gate.

No README/wiki change is required because deployed behavior is unchanged.
