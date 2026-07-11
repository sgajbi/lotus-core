# CR-1520: Timeseries Persistence Ownership

Date: 2026-07-11
Issue: #468 same-pattern architecture scan
Status: Implemented locally; runtime merge decision remains evidence-gated

## Objective

Complete the generator/aggregation persistence split and remove the transitional shared repository
without changing timeseries, aggregation, market-data, or PostgreSQL behavior.

## Implementation

- Added `TimeseriesGenerationRepository` in generator infrastructure for snapshot, cashflow, and
  position-timeseries persistence.
- Expanded `PortfolioAggregationRepository` with portfolio, epoch, as-of position-timeseries, and
  portfolio-timeseries persistence.
- Removed `SharedTimeseriesRepository` and both generic service repository wrappers.
- Reduced shared persistence to a two-read `TimeseriesMarketDataReader` and stateless position/
  portfolio upsert statement builders.
- Added framework-neutral timeseries instrument/FX records and `TimeseriesMarketDataPort`; the
  live aggregation calculation no longer imports infrastructure or persistence models through its
  port.
- Deleted the unused duplicate generator portfolio aggregation calculation and its 374-line test.
- Moved generator repository tests under infrastructure ownership and updated architecture guards
  to enforce the domain-specific aggregation repository name.

## Compatibility

No SQL predicate, upsert identity, as-of selection, market/FX lookup, aggregation result, metric
label, database schema, event, runtime topology, or downstream contract changed. Market-data ORM
rows are now mapped to immutable internal records containing only fields the calculation consumes.

## Validation

- Timeseries/aggregation/ownership unit cohorts: `83 passed`.
- Real PostgreSQL repository cohorts: `11 passed in 91.12s`.
- Aggregation boundary and ownership guards: `9 passed`.
- Scoped Ruff, formatting, MyPy, installed-source imports, and full `make architecture-guard`
  passed.
- Reconciliation onto the post-PR-727 mainline reran focused unit, ownership, boundary, MyPy, Ruff,
  architecture, documentation, and diff checks; PostgreSQL behavior remains in the aggregate gate.

## Outcome And Follow-Up

Repository ownership is ready for a future runtime-boundary assessment, but this slice does not
merge deployables. Use `lotus-core-end-state-runtime-vision.md` and gather derived-state load,
backfill, fan-in, failure-isolation, and rollback evidence before deciding keep or merge.
