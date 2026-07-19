# CR-1643: Cost-Basis Calculation Test Ownership

## Scope

- GitHub issue: #719
- Production owner: `app/domain/cost_basis/calculation/`
- Test owner: `tests/unit/services/portfolio_transaction_processing_service/domain/cost_basis/calculation/`

## Finding

Production cost-basis calculation policy had already moved from the retired calculator runtime into
the unified transaction-processing domain, but nine pure policy suites remained in the generic
`tests/.../cost/` tree. The stale test location mixed domain, application, and infrastructure
ownership and was repeated by transaction manifests, coverage standards, RFCs, and conformance
evidence.

## Decision

Move only the pure calculation family in this slice: source allocation, property invariants,
strategies, calculator policy, lot disposition, engine input, error collection, parsing, and
ordering. The suites now mirror their production package, carry responsibility docstrings, and are
protected by a no-return structure assertion. Repository and scenario-orchestration tests remain
out of scope until their true owners are handled separately.

## Same-pattern review

The review covered the complete generic cost test tree and every tracked reference to the nine
moved modules. Manifests, financial critical-path coverage, risk coverage, RFC indexes, transaction
RFCs, conformance reports, and earlier review evidence now point to the current path. The remaining
generic cost tests were deliberately retained because they do not all belong to the calculation
domain.

## Compatibility

No production module, calculation policy, API, OpenAPI schema, event, Kafka topic/group, database
schema, migration, runtime image, or downstream contract changed. Wiki source is unchanged because
operator behavior and implementation ownership were already accurate; this slice only corrects
test and evidence ownership.

## Validation

- Focused calculation, package-structure, manifest, critical-path, and RFC governance:
  `196 passed`.
- Complete transaction-processing unit package: `872 passed`.
- Governed transaction manifests: BUY `214 passed`, SELL `134 passed`, DIVIDEND `286 passed`,
  INTEREST `317 passed`, and FX `323 passed`.
- Full architecture guard, critical-path contract guard, RFC status/ledger guard, wiki/docs gate,
  scoped Ruff lint/format, retired-path scan, and `git diff --check`: passed.
