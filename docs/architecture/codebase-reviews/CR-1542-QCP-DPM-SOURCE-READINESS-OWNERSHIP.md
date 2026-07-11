# CR-1542: QCP DPM Source Readiness Ownership

## Status

Reconciled candidate on 2026-07-12. GitHub issues #464, #465, and #715 remain open until the
remaining Query Control Plane package dependencies and clean-image proof are complete.

## Objective

Move `DpmModelPortfolioTarget:v1`, `DiscretionaryMandateBinding:v1`,
`InstrumentEligibilityProfile:v1`, `PortfolioTaxLotWindow:v1`,
`MarketDataCoverageWindow:v1`, and `DpmSourceReadiness:v1` from Query Service implementation
ownership to one layered Query Control Plane capability without changing route paths or public
schemas.

## Architecture

The implemented flow is:

`QCP route -> QCP contract -> DpmSourceReadinessService -> constituent application policy ->
immutable domain evidence -> source port -> SQLAlchemy adapter -> database`

The capability owns:

1. six product-scoped public contract modules under `app/contracts`;
2. immutable, slotted, Decimal-preserving model, mandate, eligibility, tax-lot, price, and FX
   evidence under `app/domain`;
3. model-weight, mandate-review, eligibility, tax-lot paging, market staleness, and fail-closed
   aggregate policies under `app/application/dpm_source_readiness`;
4. narrow reference-data, portfolio-state, and continuation-token ports under `app/ports`;
5. deterministic effective-date, latest-observation, keyset, and bounded SQL reads under
   `app/infrastructure`;
6. one request-scoped dependency graph with shared readers, token codec, and UTC clock.

Query Service no longer owns the DPM facade, constituent policies, duplicate DTOs, DPM read model,
DPM source port, mapper functions, repository methods, latest-FX helper, or duplicate tests.

## Correctness And Runtime Improvement

The QCP adapters preserve effective-date precedence, active-target filtering, request-order
eligibility results, latest price/FX selection no later than `as_of_date`, tax-lot
`page_size + 1` reads, request-bound continuation fingerprints, and acquisition-date/lot-id
keysets. Application policies receive typed domain evidence instead of ORM-shaped `Any` values.

Every constituent response now emits an injected UTC `generated_at`, deterministic SHA-256
`content_hash`, `source_digest`, `source_batch_fingerprint`, source reference, lineage, evidence
timestamp, and freshness. Volatile generation time is excluded from the hash. Aggregate readiness
uses the latest constituent evidence timestamp and claims `CURRENT` only when all five families are
`READY`; non-ready aggregate states remain fail-closed and report `PARTIAL` freshness.

## Compatibility

The six routes, request fields, response fields, source-product identities, state precedence,
reason codes, pagination behavior, request validation, and HTTP 400/404/422 mappings are preserved.
Populating source-proof metadata and translating accepted mandate evidence to `COMPLETE` are
intentional additive evidence corrections. Downstream consumers do not need endpoint migration.

## Measurable Change

Across the 15 scoped commits from the prior CR checkpoint:

- `60` files changed;
- `4,344` lines added and `6,971` removed, a net reduction of `2,627` lines;
- the complete Query Service DPM execution branch and migration-only schema duplicates were deleted;
- QCP direct Query Service imports remain `10`, all outside this DPM capability.

## Validation

- complete Query Service/QCP unit and QCP integration surface: `1,673 passed`;
- full QCP route, dependency, and OpenAPI surface: `170 passed`;
- aggregate/new/legacy application parity checkpoint: `79 passed`;
- focused repository, adapter, and architecture checkpoint: `39 passed`;
- scoped contract, boundary-mapping, and OpenAPI checkpoint: `77 passed`;
- strict MyPy passed across contracts, domain, ports, application, adapters, dependencies, router,
  and surviving Query Service repositories;
- Ruff lint/format, architecture, application, domain, repository, adapter, mapping, and API guards
  passed;
- usage scans found no surviving Query Service production reference to the retired DPM symbols.

## Downstream Impact

No route or schema migration is required. Consumers may now validate source-owned proof metadata
and should continue treating overall readiness as an operator/workflow gate, not mandate approval,
suitability, valuation, tax advice, liquidity analysis, execution quality, best execution, or OMS
acknowledgement.

## Remaining Work

Issue #715 remains open. Benchmark/reference routes, operations/support, and advisory compatibility
still import Query Service implementation modules. Complete those ownership decisions and clean
installed-image startup/runtime proof before claiming QCP package independence.
