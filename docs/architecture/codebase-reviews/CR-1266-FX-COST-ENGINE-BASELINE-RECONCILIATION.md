# CR-1266 FX Cost Engine Baseline Reconciliation

## Objective

Fix GitHub issue #447 by reconciling the cost engine strategy table with the canonical FX
baseline processing path. `FX_SPOT`, `FX_FORWARD`, and `FX_SWAP` rows should no longer return a
generic pending implementation error when they carry canonical FX fields.

## Expected Improvement

This slice removes a duplicated and stale FX processing boundary:

1. `portfolio_common.transaction_domain.build_fx_baseline_processing_update(...)` is now the shared
   baseline update helper used by both processed-event construction and the cost engine,
2. the cost engine uses a canonical `FxBaselineStrategy` for `FX_SPOT`, `FX_FORWARD`, and `FX_SWAP`
   instead of `FxPendingStrategy`,
3. canonical FX validation runs before engine baseline updates, so invalid linkage and invalid
   component metadata still fail closed,
4. `NONE` and `UPSTREAM_PROVIDED` realized-FX-P&L modes remain supported,
5. `CASH_LOT_COST_METHOD` is explicitly rejected as an unsupported advanced mode instead of being
   silently treated like upstream-provided evidence.

## Downstream Compatibility

No route path, OpenAPI schema, database schema, Kafka topic, event type, or downstream response DTO
changed. The intentional behavior change is limited to the in-process cost engine: canonical FX rows
now receive explicit zero-cost and baseline realized-P&L fields instead of a generic pending error.

This does not implement advanced cash-lot realized FX P&L, forward-curve pricing, NDF fixing,
unrealized MTM, hedge attribution, execution quality, best execution, or OMS acknowledgement.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio_common/test_fx_baseline_processing.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py tests/unit/transaction_specs/test_fx_slice0_characterization.py -q`:
  68 passed.
- `python scripts/test_manifest.py --suite transaction-fx-contract --quiet`:
  336 passed.
- `make test-transaction-fx-contract`:
  336 passed.
- `make typecheck`:
  passed.
- `make lint`:
  passed.
- `make quality-wiki-docs-gate`:
  passed.
- `make security-audit`:
  passed; no broken requirements and no known vulnerabilities found. Local editable Lotus
  packages were skipped by `pip-audit` because they are not PyPI packages.
- `git diff --check`:
  passed with line-ending warnings only.
- `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/fx_baseline_processing.py src/libs/portfolio-common/portfolio_common/transaction_domain/__init__.py src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/libs/portfolio_common/test_fx_baseline_processing.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py tests/unit/transaction_specs/test_fx_slice0_characterization.py`:
  passed.
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/transaction_domain/fx_baseline_processing.py src/libs/portfolio-common/portfolio_common/transaction_domain/__init__.py src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/libs/portfolio_common/test_fx_baseline_processing.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py tests/unit/transaction_specs/test_fx_slice0_characterization.py`:
  passed.

## Documentation And Wiki Decision

Updated the FX conformance report, repo engineering context, and codebase review ledger. No README or
wiki source change is required because this slice changes internal engine reconciliation and test
evidence, not an operator command, public API, support runbook, or wiki navigation contract.
