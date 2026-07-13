# CR-1566 Foreign-Exchange Domain Ownership

Date: 2026-07-14

## Objective

Give foreign-exchange transaction policy one runtime owner and remove framework types from the
domain without changing FX booking, validation, linkage, cashflow, position, or P&L behavior.

## Findings

- FX models, validation, reason codes, linkage, contract-instrument construction, and baseline P&L
  policy lived under `portfolio_common.transaction_domain` although the unified transaction
  processor was their only runtime owner.
- Effective-processing policy was shared through the same compatibility package and position held
  a duplicate FX component selector.
- `FxCanonicalTransaction` inherited from Pydantic `BaseModel`, keeping framework validation inside
  domain logic and requiring an architecture-guard waiver.

## Change

- Moved FX policy into
  `portfolio_transaction_processing_service.app.domain.transaction.fx` with mirrored tests.
- Moved effective-processing selection into the service-owned transaction domain and reused it from
  cost, cashflow, and position behavior.
- Replaced the Pydantic FX model with an immutable dataclass, explicit canonicalization, and a
  structural source protocol plus `from_transaction(...)` mapper.
- Retired the now-empty shared transaction-domain package and guarded its absence.
- Updated test manifests, critical-path coverage, domain-layer enforcement, RFC-082 evidence, the
  current architecture map, repository context, and wiki source to the new owner.

## Compatibility

No API, event payload, database schema, Kafka topic, image, deployment, or runtime topology changed.
Canonical transaction codes, validation reason codes, normalized currencies/control codes,
linkage fields, and baseline realized-P&L modes are preserved.

## Validation

- Focused FX domain, transaction manifest, cost, cashflow, and position tests.
- Domain-layer, critical-path coverage, script-structure, package-ownership, and dependency guards.
- Repository Ruff/format, MyPy, unit, database, and integration lanes before PR.

## Documentation Decision

RFC-082, its conformance report, RFC index, current architecture, repository context, wiki source,
and this review record changed. README capability claims remain accurate and need no change.
