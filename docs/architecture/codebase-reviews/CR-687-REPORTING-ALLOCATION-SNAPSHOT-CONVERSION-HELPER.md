# CR-687: Reporting Allocation Snapshot Conversion Helper

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After CR-686 centralized reporting snapshot conversion for AUM and portfolio summary,
`ReportingService._resolve_allocation_rows(...)` still carried its own local snapshot native-value
collection, concurrent reporting-currency conversion, and deterministic row/value rejoin logic.
That left allocation on a separate implementation path even though the conversion semantics match
the shared reporting helper.

## Change

Routed allocation row conversion through `_snapshot_reporting_values(...)` while preserving the
existing concurrent look-through component evidence read. Parent security identifiers are still
normalized once, de-duplicated for the repository predicate, and rejoined to converted rows in
input order before direct and look-through allocation logic runs.

Existing allocation coverage continues to prove conversion and component evidence reads start
concurrently.

## Impact

This reduces duplicated reporting-service conversion logic and keeps allocation, AUM, and
portfolio-summary snapshot conversion semantics aligned while preserving response shape,
look-through behavior, parent normalization, missing-rate behavior, database schema, wiki source,
and platform contracts.

## Validation

Local validation passed:

1. focused reporting-service allocation proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
