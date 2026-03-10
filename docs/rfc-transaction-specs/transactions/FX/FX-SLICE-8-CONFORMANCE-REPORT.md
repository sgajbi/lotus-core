# FX-SLICE-8-CONFORMANCE-REPORT

## Scope
Slice 8 closes RFC 082 by wiring canonical FX coverage into the repository's standard regression surfaces and by recording the final requirement-to-evidence mapping for `FX_SPOT`, `FX_FORWARD`, and `FX_SWAP`.

## Delivered in Slice 8
1. Dedicated manifest suite added in [scripts/test_manifest.py](C:\Users\Sandeep\projects\lotus-core\scripts\test_manifest.py):
 - `transaction-fx-contract`
 - alias `fx-rfc`
2. Dedicated local targets added in [Makefile](C:\Users\Sandeep\projects\lotus-core\Makefile):
 - `test-transaction-fx-contract`
 - `test-fx-rfc`
3. CI matrix coverage added in [.github/workflows/ci.yml](C:\Users\Sandeep\projects\lotus-core\.github\workflows\ci.yml), including `transaction-fx-contract` and full-E2E execution on `main`.
4. FX query-router integration coverage extended in [test_transactions_router.py](C:\Users\Sandeep\projects\lotus-core\tests\integration\services\query_service\test_transactions_router.py) to verify FX filter forwarding.
5. FX end-to-end lifecycle coverage added in [test_fx_lifecycle.py](C:\Users\Sandeep\projects\lotus-core\tests\e2e\test_fx_lifecycle.py) for:
 - `FX_SPOT`
 - `FX_FORWARD`
 - `FX_SWAP`

## Requirement-to-Evidence Closure
| RFC-FX-01 Area | Evidence |
| --- | --- |
| Canonical FX business types | [transaction_type.py](C:\Users\Sandeep\projects\lotus-core\src\services\calculators\cost_calculator_service\app\cost_engine\domain\enums\transaction_type.py); [test_fx_slice0_characterization.py](C:\Users\Sandeep\projects\lotus-core\tests\unit\transaction_specs\test_fx_slice0_characterization.py) |
| Canonical validation and reason codes | [fx_models.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\transaction_domain\fx_models.py); [fx_validation.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\transaction_domain\fx_validation.py); [fx_reason_codes.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\transaction_domain\fx_reason_codes.py); [test_fx_validation.py](C:\Users\Sandeep\projects\lotus-core\tests\unit\libs\portfolio_common\test_fx_validation.py) |
| Deterministic linkage and enrichment | [fx_linkage.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py); [test_fx_linkage.py](C:\Users\Sandeep\projects\lotus-core\tests\unit\libs\portfolio_common\test_fx_linkage.py) |
| Cash settlement semantics | [cashflow_logic.py](C:\Users\Sandeep\projects\lotus-core\src\services\calculators\cashflow_calculator_service\app\core\cashflow_logic.py); [test_cashflow_rule_contract.py](C:\Users\Sandeep\projects\lotus-core\tests\integration\services\calculators\cashflow_calculator_service\test_cashflow_rule_contract.py); [test_cashflow_logic.py](C:\Users\Sandeep\projects\lotus-core\tests\unit\services\calculators\cashflow_calculator_service\unit\core\test_cashflow_logic.py) |
| FX contract lifecycle | [fx_contract_instrument.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\transaction_domain\fx_contract_instrument.py); [consumer.py](C:\Users\Sandeep\projects\lotus-core\src\services\calculators\cost_calculator_service\app\consumer.py); [position_logic.py](C:\Users\Sandeep\projects\lotus-core\src\services\calculators\position_calculator\app\core\position_logic.py); [test_fx_contract_instrument.py](C:\Users\Sandeep\projects\lotus-core\tests\unit\libs\portfolio_common\test_fx_contract_instrument.py); [test_position_logic.py](C:\Users\Sandeep\projects\lotus-core\tests\unit\services\calculators\position_calculator\core\test_position_logic.py) |
| Swap grouping | [fx_linkage.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py); [fx_validation.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\transaction_domain\fx_validation.py); [test_fx_linkage.py](C:\Users\Sandeep\projects\lotus-core\tests\unit\libs\portfolio_common\test_fx_linkage.py) |
| Realized FX P&L baseline | [fx_baseline_processing.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\transaction_domain\fx_baseline_processing.py); [test_cost_calculator_consumer.py](C:\Users\Sandeep\projects\lotus-core\tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py) |
| Query and observability | [transactions.py](C:\Users\Sandeep\projects\lotus-core\src\services\query_service\app\routers\transactions.py); [transaction_repository.py](C:\Users\Sandeep\projects\lotus-core\src\services\query_service\app\repositories\transaction_repository.py); [transaction_service.py](C:\Users\Sandeep\projects\lotus-core\src\services\query_service\app\services\transaction_service.py); [test_transactions_router.py](C:\Users\Sandeep\projects\lotus-core\tests\integration\services\query_service\test_transactions_router.py) |
| Persistence round-trip | [database_models.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\database_models.py); [events.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\events.py); [test_repositories.py](C:\Users\Sandeep\projects\lotus-core\tests\integration\services\persistence_service\repositories\test_repositories.py) |
| Full-stack lifecycle | [test_fx_lifecycle.py](C:\Users\Sandeep\projects\lotus-core\tests\e2e\test_fx_lifecycle.py) |

## Shared-Doc Conformance Note
Validated explicitly against:
1. `05-common-validation-and-failure-semantics.md`
2. `06-common-calculation-conventions.md`
3. `08-timing-semantics.md`
4. `09-idempotency-replay-and-reprocessing.md`
5. `10-query-audit-and-observability.md`
6. `12-canonical-modeling-guidelines.md`
7. `13-dual-leg-accounting-and-cash-adjustment-model.md`

How this slice aligns:
1. Canonical snake_case naming only; no aliases introduced.
2. FX remains outside the generic `ADJUSTMENT` pattern.
3. Query/audit evidence is exposed on existing supported surfaces rather than a side API.
4. Replay-safe identifiers remain first-class in both code and tests.

## Validation Evidence for Slice 8
Completed local gates:
1. `python -m pytest tests/unit/services/persistence_service/consumers/test_persistence_instrument_consumer.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py -q`
 - Result: `18 passed`
2. `python -m pytest tests/e2e/test_fx_lifecycle.py::test_fx_lifecycle_cash_positions_reflect_settlement_pairs -q -x`
 - Result: `1 passed`
3. `python -m pytest tests/e2e/test_fx_lifecycle.py -q`
 - Result: `3 passed`
4. `python -m pytest tests/integration/services/persistence_service/repositories/test_repositories.py::test_instrument_repository_persists_fx_contract_fields tests/integration/services/query_service/test_transactions_router.py -q`
 - Result: `6 passed`
5. `python scripts/test_manifest.py --suite transaction-fx-contract --quiet`
 - Result: `195 passed`
6. `python -m ruff check src/services/persistence_service/app/consumers/base_consumer.py src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py tests/unit/services/persistence_service/consumers/test_persistence_instrument_consumer.py tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py tests/integration/services/persistence_service/repositories/test_repositories.py`
 - Result: passed

Root-cause fixes validated by the live Docker run:
1. Instrument persistence idempotency now safely handles non-portfolio instrument events (`portfolio_id` absent) without rolling back the instrument UPSERT.
2. Cashflow rule cache now stores immutable rule snapshots rather than detached ORM entities, removing session-bound rule failures under FX traffic.
3. `FX_CONTRACT_OPEN` and `FX_CONTRACT_CLOSE` are treated as non-cash lifecycle components and therefore do not incorrectly enter cashflow generation or DLQ.

Repository-level gates expected after PR:
1. CI transaction matrix executes `transaction-fx-contract`
2. `main` pipeline executes the full E2E tree via `e2e-all`, including the FX lifecycle scenario
3. `main` also executes full integration coverage via `integration-all`

## Accepted Residuals
1. Spot realized FX P&L remains baseline-policy driven; advanced derivation modes are intentionally deferred and explicitly modeled as policy choices, not hidden behavior.
2. The E2E scenario validates lifecycle persistence, position history, and query visibility. It is not a substitute for future market-data stress/performance scenarios if institutional-scale FX throughput becomes a separate concern.

## Conclusion
RFC 082 now has the same governance shape as the mature transaction RFC families:
1. slice artifact trail,
2. dedicated contract suite,
3. CI wiring,
4. explicit conformance report,
5. E2E lifecycle evidence for the full FX family.
