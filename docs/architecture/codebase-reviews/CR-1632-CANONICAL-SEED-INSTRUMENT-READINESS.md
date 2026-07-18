# CR-1632: Canonical Seed Instrument Readiness

## Objective

Make the governed `PB_SG_GLOBAL_BAL_001` front-office reseed deterministic and repeatable by
proving parent instrument persistence before dependent reference-data ingestion and by preventing a
failed cleanup from leaving canonical data partially deleted.

## Finding

GitHub issue #805 recorded a canonical Workbench bring-up failure at
`POST /ingest/instrument-eligibility`: eligibility for `FO_BOND_UST_2030` violated the instrument
foreign key because the instrument row was not durable.

The bounded review found three defects in the same reseed lifecycle:

1. cleanup targeted `instruments.raw.received-*`, while the governed physical topic identity and
   persisted event ids use `instruments.received-*`; a stale persistence idempotency fence could
   therefore classify a new seed instrument event as already processed,
2. instrument ingestion is asynchronous, but the seed continued to eligibility and other dependent
   data without proving that every unique instrument was query-visible, and
3. cleanup omitted seven direct portfolio foreign-key children and ran as non-atomic multi-statement
   SQL, so a later failure could retain the portfolio after earlier child data was deleted.

The direct PostgreSQL foreign-key inventory confirmed the omitted portfolio children were
`average_cost_pool_state`, `cost_basis_processing_state`, `client_income_needs_schedules`,
`client_tax_profiles`, `client_tax_rule_sets`, `liquidity_reserve_requirements`, and
`planned_withdrawal_schedules`. None has a further child foreign key that changes the required
portfolio-scoped delete order.

PR Merge Gate run `29634235372` then found the same asynchronous parent-readiness defect in the
Docker endpoint smoke: it posted a transaction and immediately requested replay, while the replay
contract now resolves source identity from the durable transaction ledger. The one-shot replay POST
therefore received 404 before the asynchronous transaction consumer committed the row. The smoke
cleanup also retained the same non-atomic and incomplete portfolio-child deletion pattern.

## Change

- Corrected the local reseed fence cleanup to the physical `instruments.received-` event prefix.
- Added a bounded, deduplicated instrument-readiness wait immediately after instrument ingestion.
  Each poll queries only unresolved security ids, and timeout fails closed with the exact missing
  identifiers.
- Added every verified direct portfolio child to the cleanup order before portfolio deletion.
- Wrapped the complete portfolio, benchmark, model, index, business-date, and replay-fence cleanup
  in one PostgreSQL transaction and enabled `ON_ERROR_STOP`, so any statement failure rolls back the
  complete cleanup before the existing bounded retry runs.
- Added an exact-identity, bounded transaction-ledger readiness wait before the smoke issues its
  one-shot replay POST. A page containing another transaction does not satisfy readiness, and a
  timeout reports the requested id plus the last HTTP and ledger evidence.
- Applied the verified portfolio-child inventory, one transaction, and `ON_ERROR_STOP` behavior to
  deterministic Docker smoke cleanup as well as canonical seed cleanup.

## Compatibility

The change preserves HTTP, OpenAPI, event, database-schema, migration, topic, consumer-group,
portfolio, instrument, and reference-data contracts. It changes only local canonical seed
orchestration and cleanup safety. Successful runs retain the same governed data pack; failed runs
now stop before dependent ingestion or roll back cleanup instead of exposing partial state.

README, API inventory, supported-feature, migration, and wiki truth are unchanged. Repository
engineering context now records the reusable parent-readiness, physical-fence, and atomic-cleanup
rules. No wiki publication is required for this operator-tool implementation detail.

## Validation

- `python -m pytest tests/unit/tools/test_front_office_portfolio_seed.py -q`: 58 passed
- scoped Ruff lint and format checks: passed
- `git diff --check`: passed
- full repository MyPy scope: 235 files passed after the first implementation slice
- branch-qualified live reseed against the owned `lotus-core-app-local` stack passed the former
  instrument-eligibility foreign-key failure and restored the governed portfolio
- non-destructive branch-qualified verification completed at governed as-of date `2026-04-10`,
  with 10/10 valued positions, performance and return readiness, and no stale or failed aggregation
- full exact-head `make test-unit`: 4,847 passed, 10 deselected
- `make lint`, `make typecheck`, `make architecture-guard`, and governed documentation gates: passed
- Docker smoke fix-forward tests: 10 passed; scoped Ruff, format, MyPy, and diff checks: passed
- exact-head PR CI rerun, merge, and exact-main certification remain required before closure

Signed implementation commits: `14726920a`, `1008a6150`, `c7b9feb52`, `cdd885b28`, and
`10b985e86`.

GitHub evidence: issue #805 and
`https://github.com/sgajbi/lotus-core/issues/805#issuecomment-5010205602`.
