# Mapping And Anti-Corruption Boundary

## Purpose

Boundary mapping in `lotus-core` reconciles API DTOs, event payloads, persistence rows, read
records, and source-data response envelopes. These mappings must be explicit, tested, and safe to
change without silently changing downstream banking evidence.

## Boundary Rules

- API DTOs may be accepted at the API or ingestion edge, but application workflows should receive
  commands or validated boundary payloads rather than framework objects. Ingestion publish
  workflows should map API DTOs through named payload mappers before Kafka publication.
- Event payloads should validate through governed event models before persistence or downstream
  processing.
- Persistence repositories should map event/domain/read inputs through named mapper functions
  before constructing SQLAlchemy values.
- Persistence service consumers should decode Kafka bytes, derive deterministic message identity,
  validate Pydantic event models, and derive idempotency metadata through explicit event adapters
  before opening database units of work.
- Valuation, pipeline, persistence, and future event-consuming services should use
  `portfolio_common.event_mapping` for raw Kafka decode/model validation and outbox payload
  serialization unless a service-specific adapter adds narrower domain metadata.
- Persistence service repositories should consume adapter-owned event record values and keep only
  table-specific SQL conflict/update policy locally.
- Read rows should be mapped to explicit read records or DTOs at the query boundary, not passed as
  untyped row objects through application/domain policy.
- Source-data response envelopes must preserve product identity, version, runtime metadata,
  supportability, paging, and source lineage.
- High-value source-data products should split typed row/read-model mapping, source-evidence or
  supportability policy, and response-envelope assembly into separately testable modules before
  adding new behavior.

See [Repository Output-Shape Standard](./repository-output-shape-standard.md) for the repository
adapter rule and transitional exception register.

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

`make architecture-guard` runs `scripts/mapping_anti_corruption_guard.py` as the representative
contract index for this boundary. The guard verifies that each boundary family has a named
artifact, that issue #661 stays cross-linked with #640 and #648, and that selected inline mapping
snippets do not drift back into orchestration or persistence repositories.

`make test-boundary-mapping-conformance` runs the current mapper conformance suite. The suite is
also included in `make test-medium` and `make test-pr-suites`.

`make repository-output-shape-guard` runs the static repository output-shape guard and is included
in `make lint`.

Current coverage:

- transaction ingestion DTO to explicit published-payload mapper, headers, and body;
- business-date, portfolio, transaction, instrument, market-price, and FX-rate ingestion publish
  workflows route API DTO serialization through named payload mappers;
- JSON payload to governed `TransactionEvent`;
- Kafka message payload to persistence event adapter envelope, including event identity,
  correlation lineage, idempotency key, portfolio scope, and non-transaction fallback behavior;
- shared Kafka event mapping for valuation, pipeline, and persistence consumers, including invalid
  JSON, validation errors, Decimal/date fidelity, schema/correlation preservation, DLQ handoff, and
  outbox payload serialization;
- pipeline stage outbox event mapping through `pipeline_event_factory`, keeping event type, topic,
  aggregate identity, and serialized payload construction out of `PipelineOrchestratorService`
  while preserving the shared outbox payload adapter;
- transaction event to persistence record values;
- unknown and missing transaction event field rejection;
- typed portfolio tax-lot read-record mapping to `PortfolioTaxLotWindow:v1` source-data envelope;
- typed performance-economics read-record mapping to `PerformanceComponentEconomics:v1`, including
  missing optional cashflow evidence and multiple fee currencies;
- performance-economics source-evidence policy and response-envelope assembly, including component
  coverage, empty/partial-page supportability, data quality, lineage, runtime metadata, and
  returned-page totals.

## Follow-Up Scope

GitHub issue #665 is fixed locally pending PR CI/QA for the current conformance gate. GitHub issue
#664 is fixed locally pending PR CI/QA for typed source-data read records. GitHub issue #648 is fixed
locally pending PR CI/QA for the repository output-shape standard and static guard. GitHub issue
#662 is fixed locally pending PR CI/QA and issue closure. GitHub issue #663 is fixed locally for
the required representative `PerformanceComponentEconomics:v1` source-data product pending PR
CI/QA and issue closure. GitHub issue #661 is fixed locally for the representative
anti-corruption contract acceptance set pending PR CI/QA and issue closure: ingestion API DTO to
event payload mapping, Kafka event payload validation, persistence event-to-row mapping, typed
repository/read-record mapping, and source-data response assembly are all covered by named modules
and the boundary conformance gate. Issue #640 remains a related architecture-governance reference
for keeping API/application/domain/infrastructure boundaries explicit as future command/result
paths are migrated.
