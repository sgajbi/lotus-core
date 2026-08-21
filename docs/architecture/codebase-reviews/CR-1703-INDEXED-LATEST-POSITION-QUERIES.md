# CR-1703 - Indexed Latest Position Queries

Date: 2026-08-21
Status: Fixed locally; protected PR, exact-main validation, and issue closure pending
Issue: #505

## Finding

Position query and valuation-reprocessing readers derived the latest row per financial identity
with `row_number()` window scans. The query shapes retained current-epoch and business-date
semantics, but they made PostgreSQL rank every qualifying row before filtering to the latest one.
That work grew with retained history rather than the requested current portfolio or security set.

## Resolution

1. Query Service latest-position, latest-position-history, and snapshot-valuation reads now use
   PostgreSQL `DISTINCT ON` over normalized portfolio/security identity with deterministic
   business-date and row-id tie-breaking.
2. Current reads join `PositionState` and match its current epoch before selecting the latest row.
   Readers that derive open/closed posture from history apply the non-zero quantity predicate after
   latest-history selection, so an older open row cannot resurrect a later closed position.
3. The valuation repository applies the same shape to open-position, price-revaluation, and
   security-on-date readers. Inputs and final results remain globally deterministic.
4. Existing normalized portfolio/security/date/id indexes remain the storage authority. An
   additive, idempotent data migration restores missing `PositionState` rows for evidence created
   before epoch control existed. It derives the latest persisted epoch from history and snapshots,
   preserves every existing live state row, and starts repaired keys in `REPROCESSING` from the
   day before their earliest evidence instead of fabricating a completed watermark.
5. PostgreSQL plan tests invoke the real Query Service latest-position and valuation-reprocessing
   repository methods, capture the exact SQL sent to PostgreSQL, and explain those complete query
   shapes. They reject `WindowAgg` and sequential scans, verify the governed covering indexes
   exist, and accept PostgreSQL's cost-based choice among suitable indexes without forcing or
   overstating one exact index choice.

## Compatibility

Method signatures, public API/OpenAPI contracts, response order, current-epoch behavior,
as-of-date selection, quantity semantics, and valuation calculations are unchanged. The additive
data migration changes no table shape and is intentionally irreversible because a repaired row may
be advanced by a live processor after upgrade. Existing state is never overwritten. There is no
schema-DDL, event, Kafka, dependency, image, datastore, or topology change. The runtime change
remains an internal PostgreSQL query-shape improvement.

## Validation Evidence

- 20 focused SQL-shape and repository unit tests passed through the repository-owned Python
  launcher. They prove `DISTINCT ON`, stable ordering, current-epoch joins, and absence of
  `row_number()` across every changed reader.
- The complete Query Service position-repository PostgreSQL file passed: 6 tests in 97.29 seconds.
- Focused valuation-repository PostgreSQL behavior passed: 2 tests in 75.23 seconds, including a
  later stale-epoch row that cannot hide the current open position.
- The final representative PostgreSQL plan proof passed in 81.84 seconds against 7,500 snapshot
  rows and 7,500 history rows. It captured and explained the complete production latest-position
  and security/date reprocessing statements, including current-epoch, instrument, reconciliation,
  quantity, and outer-join predicates. Both plans used indexed access and contained neither
  `Seq Scan` nor `WindowAgg`; the normalized covering indexes were present and valid.
- The legacy-state migration contract proves both history and snapshot evidence sources, latest
  epoch selection, conservative watermark derivation, normalized-key idempotency, preservation of
  existing state, and irreversible downgrade posture. Real PostgreSQL proof runs the migration
  twice, preserves a live epoch-3 state, and verifies that a formerly unregistered epoch-0 snapshot
  remains visible through the production open-position reader.
- The protected critical-database suite passed all 85 tests in 340.78 seconds.
- Ruff check and formatting, MyPy across 318 source files, architecture/security/governance gates,
  documentation evidence, wiki/docs validation, and diff hygiene passed locally. Protected PR
  evidence, exact-main validation, and issue-loop closure must be reconciled before #505 closes.

## Same-Pattern And Governance Decision

The same-pattern scope includes the adjacent valuation/reprocessing readers in the two modified
repository owners. Broad reconciliation streaming remains under #503 and transaction economics
under #719. Measured indexed plans do not justify a materialized latest-state table in this slice.
Any future query that newly requires control-state authority for facts predating that authority must
ship upgrade-path backfill proof in the same change; current-data fixtures alone are insufficient.
No wiki change is required because no public contract, operator command, recovery procedure, or
runtime configuration changed. No central skill or platform context change is needed; this
repository-local rule makes the existing bounded-query and current-epoch governance precise.
