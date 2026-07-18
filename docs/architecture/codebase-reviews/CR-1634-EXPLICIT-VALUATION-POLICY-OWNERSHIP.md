# CR-1634: Explicit Valuation Policy Ownership

## Objective

Replace implicit position-valuation scaling with an explicit, framework-independent policy contract
that position valuation and financial reconciliation can apply identically without either service
importing the other's implementation.

## Finding

The shared valuation-unit-price helper still infers legacy bond quote scaling from product type,
price magnitude, quantity, and average cost. That inference cannot represent clean versus dirty
percent-of-principal quotes, factor-adjusted principal, listed-contract deliverables, supplied
per-contract or whole-position fair value, or the distinction between futures notional and supplied
settlement variation.

The calculation semantics have two legitimate deployable consumers: position valuation produces
the financial result and financial reconciliation independently reproduces the expected result.
Keeping separate copies would recreate methodology drift; placing the policy in either service
would create a cross-service implementation import. Under repository rule 155 and CR-1517, the
narrow framework-free contract therefore belongs in `portfolio_common.domain.valuation`.
`portfolio_common` remains a distribution boundary, not a default architecture layer.

## Change

- Added composable policy/value objects for input basis, principal basis, position scaling,
  accrued-income treatment, FX conversion, and output measure.
- Added one deterministic calculation result that keeps clean value, accrued income, total market
  value, notional exposure, and settlement variation distinct.
- Added immutable, tenant/legal-book/instrument-scoped valuation-policy assignments with exact-scope
  effective-date resolution, source-version fencing, overlap and gap rejection, deterministic
  content hashing, complete cache identity, and bounded replay-date derivation for corrections.
- Conflicting payloads that claim the same source record and assignment version fail closed instead
  of being selected by arrival time or a lexical source revision.

## Ownership Boundary

Only immutable valuation vocabulary, value objects, calculation policy, and deterministic assignment
resolution belong in the shared domain package. Ingestion DTOs, assignment persistence, approval and
migration workflows, impact previews, replay scheduling, caches, Kafka adapters, API contracts, and
service orchestration remain with their owning deployables. Before runtime wiring, production
consumer imports must prove the shared boundary; if only one deployable consumes a policy, move it
to that service's domain package.

## Compatibility

The two domain slices do not change runtime valuation behavior, HTTP/OpenAPI contracts, event
payloads, database schema, topics, deployment topology, or downstream fields. Existing correct
unit-price behavior is characterized under an explicit policy. The legacy bond heuristic remains in
the runtime path until authoritative representation and assignment facts are available; it will be
deleted rather than retained as a fallback when valuation and reconciliation are rewired.

## Validation

- 25 valuation-domain tests passed, including unit/NAV, clean and dirty percent-of-principal,
  factor-adjusted principal, per-unit/per-contract/whole-position supplied values, futures notional,
  settlement variation, FX direction, exact tenant/book/instrument assignment resolution,
  source-version fencing, overlap/gap rejection, conflicting-version rejection, cache identity, and
  backdated replay-date derivation.
- Scoped Ruff lint and formatting passed.
- Strict MyPy passed for all three valuation-domain source modules.
- The calculation-kernel commit `608751249` is signed; assignment commit evidence will be recorded
  on GitHub issue #788 after commit.

## Documentation Decision

Repository context and this review ledger change because domain ownership truth changed. No API,
OpenAPI, migration, operator workflow, README, supported-feature, or wiki truth changes in these
domain-only slices. Methodology and product/lifecycle wiki updates remain required with runtime and
source-contract implementation under #788.
