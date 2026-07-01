# Mapping And Anti-Corruption Boundary

## Purpose

Boundary mapping in `lotus-core` reconciles API DTOs, event payloads, persistence rows, read
records, and source-data response envelopes. These mappings must be explicit, tested, and safe to
change without silently changing downstream banking evidence.

## Boundary Rules

- API DTOs may be accepted at the API or ingestion edge, but application workflows should receive
  commands or validated boundary payloads rather than framework objects.
- Event payloads should validate through governed event models before persistence or downstream
  processing.
- Persistence repositories should map event/domain/read inputs through named mapper functions
  before constructing SQLAlchemy values.
- Read rows should be mapped to explicit read records or DTOs at the query boundary, not passed as
  untyped row objects through application/domain policy.
- Source-data response envelopes must preserve product identity, version, runtime metadata,
  supportability, paging, and source lineage.

Current typed read-record precedent:

- `PortfolioTaxLotWindow:v1` uses `PortfolioTaxLotReadRecord` from `query_service.app.read_models`.
  `BuyStateRepository` converts SQLAlchemy `PositionLotState` rows and transaction trade-currency
  joins into that record before the source-data service or mapper sees the data.
- `PerformanceComponentEconomics:v1` uses `PerformanceEconomicsTransactionReadRecord`,
  `PerformanceEconomicsCashflowReadRecord`, and `PerformanceEconomicsCostReadRecord`.
  `TransactionRepository` converts SQLAlchemy `Transaction`, latest optional `Cashflow`, and
  `TransactionCost` relationship rows into those records before contribution-economics source-data
  assembly sees the evidence.

## Conformance Gate

`make test-boundary-mapping-conformance` runs the current mapper conformance suite. The suite is
also included in `make test-medium` and `make test-pr-suites`.

Current coverage:

- transaction ingestion DTO to published payload headers and body;
- JSON payload to governed `TransactionEvent`;
- transaction event to persistence record values;
- unknown and missing transaction event field rejection;
- typed portfolio tax-lot read-record mapping to `PortfolioTaxLotWindow:v1` source-data envelope;
- typed performance-economics read-record mapping to `PerformanceComponentEconomics:v1`, including
  missing optional cashflow evidence and multiple fee currencies.

## Follow-Up Scope

GitHub issue #665 is fixed locally pending PR CI/QA for the current conformance gate. GitHub issue
#664 can be marked fixed locally pending PR CI/QA after final validation of the current typed
source-data read-record slice. GitHub issue #661 remains the umbrella mapping/anti-corruption
contract for continued coverage across more event families, source-data products, API DTO to command
paths, and typed read records. GitHub issue #648 remains open for broader repository output-shape
standards and static/architecture detection of ORM-row leakage.
