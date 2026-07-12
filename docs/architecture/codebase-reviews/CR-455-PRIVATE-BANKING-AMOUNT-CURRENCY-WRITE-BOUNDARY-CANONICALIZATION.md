# CR-455: Private Banking Amount-Currency Write-Boundary Canonicalization

Date: 2026-05-28

## Scope

Client tax rule-set threshold currencies, income-needs schedule currencies, liquidity reserve
requirement currencies, and planned withdrawal schedule currencies across reference-data ingestion
DTOs, upsert preparation, and route-level persistence behavior.

## Finding

Private-banking planning and policy reference data carries amount-currency pairs that feed cashflow
planning, liquidity readiness, funding evidence, policy-compliance checks, and tax rule evidence.
These currency fields were constrained by length but accepted raw caller case and whitespace. Padded
or lower-case values could become authoritative reference data and force downstream cashflow,
liquidity, and tax consumers to compensate defensively.

## Change

Reused the shared portfolio-common currency-code normalizer across private-banking amount-currency
write boundaries:

1. `ClientTaxRuleSetRecord` canonicalizes optional `threshold_currency` when threshold evidence is
   present,
2. `ClientIncomeNeedsScheduleRecord`, `LiquidityReserveRequirementRecord`, and
   `PlannedWithdrawalScheduleRecord` canonicalize required `currency` before route handling,
3. `ReferenceDataIngestionService` now canonicalizes the same fields for direct service upserts,
4. route-level integration proof verifies padded lower-case input persists as canonical `SGD` for
   tax thresholds, income needs, liquidity reserves, and planned withdrawals.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/ingestion_service/test_reference_data_dto.py -q -k "private_banking_amount_currency_records_normalize_currency or tax_rule_set or income_needs or liquidity_reserve or planned_withdrawal"`
2. `python -m pytest tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py -q -k "private_banking_amount_currency_upserts_normalize_currency or client_tax_rule_sets or client_income_needs or liquidity_reserve or planned_withdrawal"`
3. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k ingest_private_banking_amount_currency_records_normalize_currency`
4. `python -m ruff check src/services/ingestion_service/app/DTOs/reference_data_dto.py src/services/ingestion_service/app/services/reference_data_ingestion_service.py tests/unit/services/ingestion_service/test_reference_data_dto.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
5. `python -m pytest tests/unit/services/ingestion_service -q`
6. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
7. `git diff --check`

Results:

1. Focused DTO pytest: `12 passed, 22 deselected`
2. Focused reference-data service pytest: `4 passed, 26 deselected`
3. Focused ingestion router pytest: `4 passed, 208 deselected`
4. Touched-surface ruff: passed
5. Ingestion-service unit pack: `120 passed`
6. Ingestion router integration pack: `212 passed`
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: valid private-banking amount-currency values are
canonicalized and invalid non-three-letter values are rejected before persistence.
