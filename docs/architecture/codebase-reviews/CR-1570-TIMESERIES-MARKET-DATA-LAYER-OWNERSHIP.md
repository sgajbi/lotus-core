# CR-1570: Timeseries Market-Data Layer Ownership

## Objective

Place the retained timeseries market-data records, capability port, and SQL reader in the narrowest
truthful domain, application, and infrastructure owners without deciding the separate runtime
consolidation question.

## Finding

CR-1520 correctly reduced shared timeseries persistence to two immutable records, a read protocol,
and a focused SQL reader. The records and reader are reused by timeseries generation and portfolio
aggregation, but the protocol itself has one application consumer: portfolio aggregation logic.
Keeping both `domain/timeseries_market_data.py` and `ports/timeseries_market_data.py` as flat shared
modules obscured the market-data context, and keeping a single-consumer port in `portfolio_common`
overstated shared ownership.

## Change

1. Moved `TimeseriesInstrument` and `TimeseriesFxRate` to
   `portfolio_common.domain.market_data.timeseries`.
2. Moved `TimeseriesMarketDataPort` to
   `portfolio_aggregation_service.app.ports.timeseries_market_data`, its sole application owner.
3. Retained `TimeseriesMarketDataReader` under shared infrastructure because both service-owned SQL
   repositories reuse its instrument and FX reads.
4. Kept generation and aggregation repositories, persistence, queues, and runtime entrypoints
   service-owned.
5. Added import/path guards for both retired flat modules and the rejected shared-port placement.
6. Added the aggregation market-data capability to the governed application-port catalog.

## Compatibility

No calculation, ordering, SQL predicate, table, migration, API, event, topic, queue, image, or
deployment behavior changed. The move is design-time modularity only and is not evidence for merging
the timeseries generator and portfolio aggregation deployables.

## Validation

- generator and aggregation unit suites after the domain move: `77 passed`;
- aggregation and package-ownership suites after port correction: `48 passed`;
- package ownership and retired-path guard: `5 passed`;
- focused strict MyPy over domain records and the service port: passed;
- focused Ruff lint/format, retired-import scans, and `git diff --check`: passed.

## Documentation Decision

Repository context, domain-layer guidance, application-port guidance, and the port capability
catalog changed because package ownership changed. README, OpenAPI, supported-features material,
and wiki source require no change because external capability and operator truth are unchanged.
