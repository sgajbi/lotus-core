# CR-1166 Cost Transaction Datetime Normalization

## Objective

Reduce cost-engine domain model complexity while making transaction datetime normalization explicit
and directly tested.

## Baseline Risk

`Transaction.standardize_datetimes(...)` mixed null handling, ISO text normalization, `Z` suffix
handling, parsing, naive-datetime UTC marking, and passthrough behavior in one B-ranked Pydantic
validator. The behavior was important for downstream cost-engine ordering and settlement semantics
but was only indirectly covered by broader cost tests.

## Change

Extracted focused helper functions in
`src/services/calculators/cost_calculator_service/app/cost_engine/domain/models/transaction.py`:

- `_iso_datetime_text(...)`
- `_parse_datetime_text(...)`
- `_utc_aware_datetime(...)`
- `standardize_datetime_value(...)`

The Pydantic validator now delegates to the helper policy.

## Expected Improvement

The cost transaction domain model is simpler and easier to verify:

- `Transaction.standardize_datetimes(...)` is reduced from `B (6)` to `A (1)`,
- `Transaction` is reduced from `B (7)` to `A (2)`,
- every function/class in the module is A-ranked,
- datetime normalization behavior has direct regression coverage.

## Compatibility And Behavior

Existing behavior is preserved:

- `Z` suffix strings parse as UTC-aware datetimes,
- naive datetime inputs are marked UTC,
- aware datetime offsets are preserved,
- `None` settlement dates remain accepted.

No product runtime contract, API, OpenAPI, database schema, data product, or downstream response
shape changed.

## Tests Added

Added `tests/unit/services/calculators/cost_calculator_service/engine/test_transaction_model.py`
with coverage for `Z` suffix parsing, naive datetime UTC marking, aware offset preservation, and
nullable settlement date behavior.

## Validation

```powershell
python -m pytest tests\unit\services\calculators\cost_calculator_service\engine\test_transaction_model.py -q
python -m pytest tests\unit\services\calculators\cost_calculator_service\engine -q
python -m ruff check src\services\calculators\cost_calculator_service\app\cost_engine\domain\models\transaction.py tests\unit\services\calculators\cost_calculator_service\engine\test_transaction_model.py
python -m ruff format --check src\services\calculators\cost_calculator_service\app\cost_engine\domain\models\transaction.py tests\unit\services\calculators\cost_calculator_service\engine\test_transaction_model.py
python -m radon cc src\services\calculators\cost_calculator_service\app\cost_engine\domain\models\transaction.py -s
python -m radon mi src\services\calculators\cost_calculator_service\app\cost_engine\domain\models\transaction.py -s
make quality-complexity-gate
make quality-maintainability-gate
```

Observed:

- focused transaction model tests: `4 passed`
- broader cost-engine unit folder: `96 passed`
- Ruff lint passed
- Ruff format check passed
- Radon reports every function/class A-ranked and module maintainability `A (57.30)`
- `make quality-complexity-gate` passed
- `make quality-maintainability-gate` passed

## Documentation Decision

Updated the codebase review ledger, quality scorecard, and refactor health report. No README or wiki
update was needed because this is internal domain-model normalization with no operator-facing
workflow or supported-capability change.
