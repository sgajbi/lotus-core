# CR-1699 - Bounded DPM Source Cardinality

Date: 2026-08-21
Status: Fixed locally; protected PR, exact-main, wiki publication, and issue closure pending
Issues: #972 and #976

## Finding

Standalone eligibility and tax-lot requests accepted caller-sized security collections, while
their persistence adapters emitted one caller-sized `IN` predicate. Separately, composed DPM
readiness materialized every effective model target before enforcing the evaluated-universe limit.
The latter could consume unbounded source rows before returning the intended fail-closed posture.

## Resolution

1. Contract-owned eligibility and tax-lot limits publish `maxItems=1000` and reject oversized
   callers through the standard validation response.
2. Eligibility, tax-lot, and returned-lot instrument-reference readers normalize, deduplicate,
   order, and chunk direct/internal collections with the shared 1,000-row/32,000-bind authority.
3. Tax-lot chunks retain identical as-of, status, and keyset predicates; Core globally orders their
   results before applying `page_size + 1`, preserving deterministic pagination.
4. Model-target reads use deterministic instrument order and `LIMIT 1001`. A typed read result
   discards the sentinel set on overflow so it cannot become publishable target authority.
5. Source overflow returns `MODEL_TARGET_LIMIT_EXCEEDED` with no targets and makes composed
   readiness skip eligibility, tax-lot, and market-data reads with
   `DPM_MODEL_TARGET_LIMIT_EXCEEDED`. Supported universes and canonical behavior are unchanged.
6. Multi-statement support events use governed low-cardinality operation labels and scalar counts;
   business identifiers are neither labels nor message content.

## Compatibility

Supported requests and model universes retain response order, paging, lineage, content identity,
supportability, and calculations. Oversized public filters now fail validation intentionally;
oversized source-owned target universes fail closed without caller blame or silent truncation.
There is no schema/migration, event, Kafka, calculation, dependency, image, datastore, or topology
change.

## Validation Evidence

- 68 focused QCP contract, adapter, and application tests passed.
- Two focused OpenAPI schema tests passed and publish both new request limits.
- The complete real-PostgreSQL source-capacity file passed: 3 tests in 66.37 seconds, covering
  exact-limit eligibility/tax-lot/instrument-reference reads and model-target ceiling overflow.
- `make typecheck` passed with no issues across 318 source files.
- Ruff, format, diff hygiene, repository-native gates, wiki premerge check, protected PR, exact-main,
  wiki publication/parity, and issue-loop closure remain pending and must be reconciled here before
  #972 or #976 closes.

## Same-Pattern And Governance Decision

#961 remains the closed owner for price/FX coverage; #503 owns reconciliation reads; #719 owns
transaction economics; #714 owns broader derived-state topology. No new central skill or platform
context rule is needed: CR-1695 and the repository context already govern caller-sized statement
batching. This review adds only DPM-specific contract and source-cardinality truth.
