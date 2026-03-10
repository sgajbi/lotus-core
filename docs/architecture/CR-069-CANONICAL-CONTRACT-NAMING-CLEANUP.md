# CR-069 Canonical Contract Naming Cleanup

## Scope
Remove stale current-state references to deleted transaction suite aliases and align active docs/tooling to the canonical transaction contract names.

## Findings
- `scripts/test_manifest.py` had already removed suite aliases, but active RFCs, conformance reports, and the `Makefile` still referenced deleted names such as `buy-rfc`, `sell-rfc`, and `fx-rfc`.
- This left current-state documentation and entrypoints out of sync with the live CI matrix and the canonical manifest vocabulary.
- Historical review records may still mention the aliases as evidence of what was removed; those are intentionally historical and not current-state drift.

## Changes
1. Removed legacy alias targets from `Makefile`.
2. Updated active RFCs and conformance reports to use canonical suite names:
   - `transaction-buy-contract`
   - `transaction-sell-contract`
   - `transaction-dividend-contract`
   - `transaction-interest-contract`
   - `transaction-fx-contract`
   - `transaction-portfolio-flow-bundle-contract`
3. Regenerated `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` so the vocabulary artifact reflects the current OpenAPI surface after the recent Swagger-depth work.

## Validation
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
- `python -m pytest tests/unit/services/query_service/test_test_manifest.py -q`
- `rg` confirmation that alias strings remain only in the historical `CR-068` review note

## Residual Risk
- Historical RFCs and review records may intentionally preserve prior terminology when describing the migration away from aliases. Do not rewrite those unless they are presented as current-state guidance.
