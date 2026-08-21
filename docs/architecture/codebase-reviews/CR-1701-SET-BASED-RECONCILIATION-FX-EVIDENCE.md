# CR-1701 - Set-Based Reconciliation FX Evidence

Date: 2026-08-21
Status: Merged and exact-main validated; closure evidence reconciled
Issue: #504

## Finding

Timeseries integrity reconciliation loaded authoritative position rows and resolved the latest FX
rate inside the position loop. A process-local cache avoided repeat reads for an identical
currency-pair/date key, but database query count still grew with the number of distinct keys in a
portfolio-day scope. Day-end controls could therefore spend most of their time on point lookups
instead of independent financial verification.

## Resolution

1. The application now derives normalized, immutable `FxRateLookupKey` values for all authoritative
   rows before aggregation and asks the evidence-reader port for the complete unique key set once.
2. The SQLAlchemy adapter globally normalizes, deduplicates, and sorts the keys, then uses a
   PostgreSQL `VALUES` relation with one lateral latest-rate lookup per key. Rate-date and stable ID
   ordering preserve the existing point-in-time selection rule.
3. Direct/internal oversized inputs use the shared 1,000-row/32,000-bind statement authority. The
   three binds per key and the lateral `LIMIT` bind are fully accounted for, and multi-statement
   evidence retains an identifier-free governed operation label.
4. Missing and non-positive FX evidence still contributes no converted amount; same-currency and
   incomplete-currency rows still use the established no-conversion path. Financial formulas,
   tolerance, finding shape, and completion posture are unchanged.
5. The superseded single-row ORM-output guard exception was removed. The batched reader publishes
   an explicit immutable-key-to-decimal mapping and no longer crosses the repository boundary with
   `FxRate` ORM rows.

## Validation Evidence

- 47 focused repository and reconciliation-service tests pass. A 200-position regression proves
  two unique pair/date keys result in one batch call, while missing/non-positive evidence preserves
  the prior fail-closed arithmetic.
- Unit query-shape proof covers normalized functional-index predicates, point-in-time fencing,
  stable latest-rate ordering, lateral joining, empty-input zero I/O, duplicate collapse, and the
  1,000/1 boundary with exact bind counts.
- A real-PostgreSQL proof resolves multiple pairs and as-of dates, including missing evidence, in
  exactly one statement and returns the expected historical rates. The complete repository file
  passes (`3 passed`), and the route-level timeseries-integrity pack preserves all four established
  success/finding postures (`4 passed`).
- The reconciliation repository PostgreSQL suite is now part of the protected
  `critical-db-coverage` manifest; its manifest contract and the full financial-reconciliation unit
  pack pass (`118 passed`). The complete protected manifest passes (`87 passed`).
- Full MyPy passes across 318 source files; repository-wide lint, strict architecture, focused
  Ruff, and diff hygiene pass.
- PR #981 passed its protected checks at exact head
  `b5d676fd477cddf8d86cbbce213fb26b4a6dfde3`, then merged by rebase as exact main
  `80be01753f86b1c6774d856f6d32efe5182056ee`. Main Releasability `32480746388`
  completed successfully at that exact SHA with zero failed or cancelled jobs.

## Compatibility And Scope

There is no route, request/response DTO, OpenAPI, schema/migration, event/Kafka, calculation,
application/runtime dependency, image, datastore, or topology change. The repository port changes
only an internal single-key evidence method into a set-based method. This PR also carries the
separately governed CI-only installer remediation recorded in CR-1702; it does not alter runtime
dependency closure. The existing Financial Reconciliation wiki already describes the
operator-visible control and no command, response, or operating procedure changed, so no wiki
source change is required.

The implementation branch was patch-equivalent to main before removal. Final issue closure follows
this durable reconciliation reaching validated main and final repository hygiene.

The same-pattern scan found that timeseries integrity still loads authoritative rows and snapshot
counts per reconciliation scope key. That broader high-cardinality reconciliation read boundary is
owned by #503; it is not hidden inside or claimed closed by this focused FX fix.
