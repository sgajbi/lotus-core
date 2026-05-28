# CR-451: Cash Account Write-Boundary Currency Canonicalization

Date: 2026-05-28

## Scope

Cash-account reference-data ingestion DTOs, reference-data upsert preparation, OpenAPI schema
truth, and ingestion-route persistence behavior.

## Finding

Cash account master data anchors cash balance, settlement, liquidity, FX readiness, and cash
account drilldown products. `account_currency` was accepted as raw caller text in the reference
data write path, so padded or lower-case values could be persisted into cash-account master data
and then require defensive cleanup in downstream cash and liquidity calculations.

## Change

Reused the shared portfolio-common currency-code normalizer at the cash-account write boundaries:

1. `CashAccountMasterRecord` validates and canonicalizes `account_currency` before route handling,
2. `ReferenceDataIngestionService.upsert_cash_account_masters(...)` canonicalizes direct service
   input before constructing the database upsert,
3. the OpenAPI schema now states that cash-account currency is canonical calculation input for
   cash balance, settlement, liquidity, and FX readiness products.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py -q -k cash_account`
2. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k cash_account_masters`
3. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q -k cash_account_master`
4. `python -m ruff check src/services/ingestion_service/app/DTOs/reference_data_dto.py src/services/ingestion_service/app/services/reference_data_ingestion_service.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`
5. `python -m pytest tests/unit/services/ingestion_service -q`
6. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
7. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
8. `git diff --check`

Results:

1. Focused reference-data service pytest: `1 passed, 18 deselected`
2. Focused ingestion router pytest: `2 passed, 205 deselected`
3. Focused OpenAPI contract pytest: `1 passed, 29 deselected`
4. Touched-surface ruff: passed
5. Ingestion-service unit pack: `98 passed`
6. Ingestion router integration pack: `207 passed`
7. Ingestion OpenAPI contract pack: `30 passed`
8. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: valid cash-account currency values are
canonicalized and invalid non-three-letter values are rejected before persistence.
