# Portfolio Flow Bundle Slice 0 Gap Assessment

## Scope

This assessment captures current `lotus-core` behavior for the bundled portfolio-level flow types before RFC-074 behavior changes:

1. `FEE`
2. `TAX`
3. `DEPOSIT`
4. `WITHDRAWAL`
5. `TRANSFER_IN`
6. `TRANSFER_OUT`

Status labels:

- `COVERED`
- `PARTIALLY_COVERED`
- `NOT_COVERED`

Behavior labels:

- `MATCHES`
- `PARTIALLY_MATCHES`
- `DOES_NOT_MATCH`

## Requirement Matrix

| Requirement | Implementation Status | Behavior Match | Current Observed Behavior | Target Behavior | Risk if Unchanged | Proposed Action | Blocking |
|---|---|---|---|---|---|---|---|
| All six bundle types treated as portfolio-level flows | PARTIALLY_COVERED | PARTIALLY_MATCHES | Cashflow rules mostly classify as portfolio flow, but `TAX` seed is `is_portfolio_flow=false`. | All six classified as portfolio-level flows in canonical rules. | Analytics classification drift for `TAX`. | Align migration/seed and rule consumers in Slice 2. | Yes |
| No `AUTO_GENERATE` dependency for this bundle | NOT_COVERED | DOES_NOT_MATCH | No bundle-level guardrail currently enforces this policy explicitly. | Explicitly reject or fail-fast on invalid mode usage for bundle types. | Ambiguous behavior if unsupported mode appears upstream. | Add validation/policy guardrails in Slice 1. | Yes |
| Portfolio-level flows should not mutate security position quantity/cost | PARTIALLY_COVERED | DOES_NOT_MATCH | Position calculator currently mutates quantity/cost for all six bundle types with type-specific logic. | Position effects harmonized with canonical semantics (portfolio cashflow semantics, no unintended position drift). | Quantity/cost basis drift in downstream position analytics. | Harmonize position semantics in Slice 3. | Yes |
| Cashflow sign and classification deterministic for each type | PARTIALLY_COVERED | PARTIALLY_MATCHES | Sign logic exists and is mostly deterministic; transfer direction depends on type and `TAX` portfolio-flow flag is inconsistent. | Canonical sign/classification/timing behavior for all six types. | Inconsistent reporting and timeseries rollups. | Rule alignment + cashflow regression tests in Slices 2-3. | Yes |
| Query/supportability explains outcomes for all six | PARTIALLY_COVERED | PARTIALLY_MATCHES | Generic query views exist; no explicit bundle-level diagnostics and evidence mapping. | Clear, test-backed query behavior for all six with supportability fields. | Slower operations/debugging for transaction disputes. | Add query/contract coverage in Slice 4. | No |

## Characterization Coverage Added in Slice 0

1. Position calculator baseline locks:
 - `DEPOSIT` currently increases quantity/cost by gross amount.
 - `WITHDRAWAL`, `FEE`, `TAX` currently decrease quantity/cost by gross amount.
 - `TRANSFER_IN` currently increases quantity by transaction quantity and cost by gross amount.
 - `TRANSFER_OUT` currently decreases quantity by transaction quantity and updates cost by `net_cost`.
2. Cashflow calculator baseline locks:
 - Deterministic sign behavior for each bundle type using current classification rules.
 - `TAX` currently remains negative under `EXPENSE`, and rule flags propagate as-is.

## Shared-Doc Conformance Note (Slice 0)

Validated against shared standards for characterization-first delivery:

1. `shared/04-common-processing-lifecycle.md`
2. `shared/05-common-validation-and-failure-semantics.md`
3. `shared/06-common-calculation-conventions.md`
4. `shared/10-query-audit-and-observability.md`
5. `shared/11-test-strategy-and-gap-assessment.md`

## Important Transition Rule

Slice 0 locks current behavior for safe refactoring only.
As slices progress, these assertions must move to canonical RFC-074 semantics and legacy-only expectations must be removed.
