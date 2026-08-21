# CR-1698: Bounded DPM and Aggregation Batches

Date: 2026-08-21
Issues: #961, #962
Status: Fixed locally; protected PR, exact-main, and wiki publication evidence pending

## Finding

Two caller-sized persistence boundaries remained after CR-1695. QCP accepted unbounded DPM
instrument and FX-pair collections and sent each collection through one price or FX predicate.
Portfolio aggregation selected every expired lease and updated caller-sized identifier sets. Both
paths could exceed a safe PostgreSQL bind/memory envelope, and model-target expansion could make an
otherwise valid readiness request exceed the leaf market-data contract after mandate/model reads.

## Resolution

- Contract-owned DPM constants cap instruments and FX pairs at 1,000 for both direct coverage and
  source-readiness requests; OpenAPI publishes the limits. Currency members now enforce the
  claimed alphabetic ISO 4217 shape and both requests reject duplicate pairs.
- QCP normalizes, deduplicates, globally sorts, and chunks market-price and FX reads through the
  shared 1,000-row/32,000-bind authority. Result ordering and application-owned request ordering
  remain deterministic.
- If caller instruments union model targets exceeds 1,000, readiness performs none of the
  eligibility, tax-lot, or market-data reads. All three families fail closed with
  `DPM_EVALUATED_INSTRUMENT_LIMIT_EXCEEDED`; Core publishes no truncated universe.
- Aggregation recovery locks an ordered 1,000-row expired cohort with `FOR UPDATE SKIP LOCKED`.
  Retry-exhausted and retryable identifiers are disjoint, sorted, deduplicated, and updated through
  shared bind-safe chunks while the scheduler provider retains transaction ownership.

## Evidence

- 67 focused request, policy, adapter, and aggregation unit tests pass.
- OpenAPI assertions prove `maxItems=1000` on both collections in both public requests.
- Real PostgreSQL maximum-input price and FX reads execute exactly one statement each and return
  all 1,000 records in deterministic order.
- Real PostgreSQL aggregation evidence drains a 1,001-row backlog as 1,000 then 1 and proves an
  injected second-chunk failure rolls back all 1,001 staged updates: 3 passed in 78.33 seconds.
- Focused Ruff/format and diff hygiene pass. Repository-native type, architecture, contract,
  protected PR, exact-main, and wiki gates remain pending.

## Compatibility and Boundaries

Supported requests retain their response, evidence, freshness, and content-identity semantics.
Oversized public requests now intentionally receive the standard validation response; source-owned
model expansion fails as readiness `UNAVAILABLE` rather than blaming the caller or truncating.
Aggregation changes only internal recovery query shape and per-cycle counts. There is no database
schema/migration, event/Kafka, calculation, dependency, image, datastore, or topology change.

#972 owns standalone eligibility/tax-lot filters, #503 owns reconciliation reads, #719 owns
transaction economics, and #714 owns broader derived-state topology/capacity. Existing platform
governance already mandates contract-owned capacity and repository-owned bind safety, so no central
skill or platform-context change is required.

