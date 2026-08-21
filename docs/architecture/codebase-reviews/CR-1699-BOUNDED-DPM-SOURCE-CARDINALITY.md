# CR-1699 - Bounded DPM Source Cardinality

Date: 2026-08-21
Status: Merged and exact-main validated; issue closure reconciliation pending
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

- 70 focused QCP contract, adapter, application, OpenAPI, HTTP validation, and statement-batching
  tests passed. They publish both new request limits, reject 1,001-item requests before dispatch,
  and prove multi-statement DPM support events contain no source identifiers.
- The complete real-PostgreSQL source-capacity file passed: 3 tests in 77.30 seconds, covering
  exact-limit eligibility/tax-lot/instrument-reference reads, exactly 1,000 supported model
  targets, and 1,001-target source overflow.
- `make typecheck` passed with no issues across 318 source files.
- `make lint`, `make architecture-guard`, `make quality-wiki-docs-gate`,
  `make docs-evidence-pack`, Ruff formatting, and diff hygiene passed.
- The governed wiki premerge check passed with the one intentional unpublished
  `Mesh-Data-Products.md` source change.
- PR #979 passed all 45 checks at exact head `e657dac02a45465344e395ffdfb2842ffa1c063a`,
  including Remote Feature Lane `32464430564` and Pull Request Merge Gate `32464451357`, then
  merged by rebase as exact main `21a2c59183ffd74bcfa2467415de807e374ddaf0`.
- Authored wiki publication `1f858768f598e2ae7225c365b0227c13cd88645f` includes the DPM
  source-cardinality truth and strict parity is zero.
- Main Releasability run `32467907834` completed successfully at exact merge SHA
  `21a2c59183ffd74bcfa2467415de807e374ddaf0`. Cumulative Main Releasability
  `32480746388` also passed at `80be01753f86b1c6774d856f6d32efe5182056ee` after the
  subsequent CI and reconciliation changes. Issue-loop closure remains gated only on this durable
  reconciliation reaching validated main and final branch/worktree hygiene.

## Same-Pattern And Governance Decision

#961 remains the closed owner for price/FX coverage; #503 owns reconciliation reads; #719 owns
transaction economics; #714 owns broader derived-state topology. No new central skill or platform
context rule is needed: CR-1695 and the repository context already govern caller-sized statement
batching. This review adds only DPM-specific contract and source-cardinality truth.
