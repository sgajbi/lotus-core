# CR-1204 Portfolio Tax-Lot Instrument Supportability

Date: 2026-06-30

## Scope

`PortfolioTaxLotWindow:v1` read-side supportability for returned position lot-state rows.

## Finding

GitHub issue #674 still had a lot-state read-side gap after the cost-consumer write guard and the
transaction-ledger supportability slice. `PortfolioTaxLotWindow:v1` could return historical or
orphan `position_lot_state` rows as ready tax-lot evidence even when the returned lot `security_id`
did not resolve to governed `instruments` master data.

That weakens downstream DPM, tax-lot, performance-economics, and advisory supportability because
the lot is visible but lacks governed product reference context.

## Action Taken

Added returned-lot instrument-reference supportability to `PortfolioTaxLotWindow:v1`:

1. the tax-lot resolver now checks returned lot security ids against governed instrument master
   data;
2. returned lots with missing instrument master references degrade supportability to
   `DEGRADED`, reason `TAX_LOTS_INSTRUMENT_REFERENCE_MISSING`, and
   `data_quality_status=PARTIAL`;
3. the supportability object now carries additive bounded fields:
   - `reason_codes`,
   - `missing_instrument_reference_count`,
   - `missing_instrument_security_ids`;
4. requested-security missing-lot support remains separate as `missing_security_ids`;
5. tax-lot security-id normalization now deduplicates before query predicates and instrument
   lookup.

The reusable platform pattern is the same as CR-1203: source-data products should preserve legacy
evidence while explicitly degrading reference supportability when master data is unavailable.

## Compatibility

The API change is additive. Existing request shape, lot rows, pagination, sorting, lineage,
requested-security missing-lot behavior, database schema, and cost-basis values are preserved.

The intentional behavior change is that a returned tax-lot page with unresolved instrument master
references is no longer classified as `READY` or `COMPLETE`.

## Evidence

Focused behavior proof:

- `python -m pytest tests/unit/services/query_service/services/test_portfolio_tax_lot_window.py tests/unit/services/query_service/repositories/test_buy_state_repository.py -q`
- Result: `26 passed`

Focused static proof:

- `python -m ruff check src/services/query_service/app/repositories/buy_state_repository.py src/services/query_service/app/services/portfolio_tax_lot_window.py src/services/query_service/app/dtos/reference_integration_portfolio_tax_lot_dto.py tests/unit/services/query_service/services/test_portfolio_tax_lot_window.py tests/unit/services/query_service/repositories/test_buy_state_repository.py`
- Result: passed
- `python -m ruff format --check src/services/query_service/app/repositories/buy_state_repository.py src/services/query_service/app/services/portfolio_tax_lot_window.py src/services/query_service/app/dtos/reference_integration_portfolio_tax_lot_dto.py tests/unit/services/query_service/services/test_portfolio_tax_lot_window.py tests/unit/services/query_service/repositories/test_buy_state_repository.py`
- Result: passed
- `make typecheck`
- Result: passed, no issues in 50 source files
- `make openapi-gate`
- Result: passed
- `make api-vocabulary-gate`
- Result: passed
- `make quality-wiki-docs-gate`
- Result: passed
- `git diff --check`
- Result: passed
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- Result: failed because the published GitHub wiki is not synchronized with repo-authored wiki
  source. Reported drift: `Data-Models.md`, `Event-Replay-Service.md`,
  `Financial-Reconciliation.md`, `Ingestion-Service.md`, `Mesh-Data-Products.md`,
  `Operations-Runbook.md`, `Outbox-Events.md`, `Validation-and-CI.md`.

## Residual Risk

This slice covers `PortfolioTaxLotWindow:v1` returned lot rows. CR-1255 adds the raw transaction
persistence policy outside the cost-consumer path; final #674 closure still requires PR/CI/QA and
post-merge wiki publication evidence.

## Documentation And Wiki Decision

Updated the implementation-backed tax-lot methodology and repo-authored mesh data products wiki
source because the source product supportability contract now includes additive instrument-reference
fields.

## Bank-Buyable Control Movement

This slice improves:

1. DPM/tax-lot source-product supportability for unresolved instrument references,
2. deterministic data-quality classification for legacy or orphan lot-state rows,
3. bounded downstream diagnostics without hiding source evidence,
4. reusable read-side degraded-reference behavior across transaction and lot source products.

This slice does not claim complete closure of issue #674 by itself; closure also depends on
CR-1201, CR-1203, and CR-1255 evidence.
