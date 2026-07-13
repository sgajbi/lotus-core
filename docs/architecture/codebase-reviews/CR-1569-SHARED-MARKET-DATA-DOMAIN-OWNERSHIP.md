# CR-1569: Shared Market-Data Domain Ownership

## Objective

Give framework-independent FX-rate validity, market-price validity, and valuation-unit-price
policies an explicit bounded-context owner instead of leaving them as unrelated modules at the
`portfolio_common` package root.

## Finding

The three policies had genuine consumers across position valuation, financial reconciliation, and
portfolio aggregation, so moving them into any one service would create the wrong owner. Their
root-level placement, however, obscured that they were pure domain policies and made the shared
package easier to extend as a flat utility bucket. Their tests also lived in a legacy hyphenated
test directory instead of mirroring the production package.

The valuation-unit-price policy still contains the separately tracked legacy bond quote heuristic.
Changing that methodology during a structural move would combine ownership and behavioral risk;
issue #451 retains that explicit calculation-policy decision.

## Change

1. Added `portfolio_common.domain.market_data` with explicit `fx_rate`, `market_price`, and
   `valuation_unit_price` modules.
2. Moved the existing policies without changing Decimal coercion, positive-value fences, bond
   quote alignment, error behavior, or return values.
3. Migrated every valuation, reconciliation, and aggregation consumer directly to the bounded
   package.
4. Mirrored tests under `tests/unit/libs/portfolio_common/domain/market_data` and added module
   docstrings to every new file.
5. Deleted the three flat roots without transitional re-exports and added AST/path guards that
   reject their reintroduction.
6. Named the normalized valuation price separately, removing an optional-to-required assignment
   exposed by strict typing while preserving runtime behavior.

## Compatibility

No HTTP API, event schema, database schema, topic, deployment topology, calculation result,
rounding policy, or operational workflow changed. The deleted Python roots were repository-internal
and all tracked consumers were migrated in the same slice.

Historical review records continue to name the paths that existed when their evidence was created.
They are archival proof, not current implementation guidance.

## Validation

- affected market-data, valuation, reconciliation, and aggregation tests: `127 passed`;
- canonical market-data and valuation tests after formatting: `29 passed`;
- package ownership and retired-path guard: `5 passed`;
- focused Ruff lint and format: passed;
- focused strict MyPy over shared Decimal and market-data policy: passed;
- retired-import scan and `git diff --check`: passed.

## Documentation Decision

Repository context and the domain-layer contract changed because code-placement truth changed.
README, OpenAPI, API inventory, supported-features material, and wiki source require no change
because externally supported behavior and operations are unchanged.
