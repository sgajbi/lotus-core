# CR-958: Reference Data Tax Rule Validator Boundary

Date: 2026-06-05

## Scope

Move client tax rule-set validation branches into named helper functions without changing
`ClientTaxRuleSetRecord`, request fields, schema names, threshold-pair semantics, effective-window
semantics, or bounded-evidence requirements.

## Finding

`ClientTaxRuleSetRecord.validate_rule` mixed effective-window validation, threshold amount/currency
pair validation, and bounded rule-evidence validation in one C-ranked Pydantic validator. The
method reported `C (12)`, making the already large `reference_data_dto.py` module harder to review.

## Action

Added focused helper functions inside `reference_data_dto.py`:

- `_validate_tax_rule_effective_window`
- `_validate_tax_rule_threshold_pair`
- `_validate_tax_rule_evidence`

`ClientTaxRuleSetRecord.validate_rule` now delegates to those helpers and remains as the public
Pydantic validator boundary. Added explicit tests for both threshold-pair directions and invalid
effective windows.

## Result

`ClientTaxRuleSetRecord.validate_rule` improved from `C (12)` to `A (1)`, removing the only
C-ranked method from `reference_data_dto.py`. The extracted tax-rule evidence helper reports
`B (6)`, threshold-pair helper `A (5)`, and effective-window helper `A (3)`. The module remains
`C (0.00)` under Radon maintainability because of its size and remaining B-ranked DTO classes and
validators.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\test_reference_data_dto.py -q`
  => 35 passed
- `python -m ruff check src\services\ingestion_service\app\DTOs\reference_data_dto.py tests\unit\services\ingestion_service\test_reference_data_dto.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\DTOs\reference_data_dto.py tests\unit\services\ingestion_service\test_reference_data_dto.py`
  => 2 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\DTOs\reference_data_dto.py`
  => 1,686 SLOC
- `python -m radon mi src\services\ingestion_service\app\DTOs\reference_data_dto.py -s`
  => `C (0.00)`
- `python -m radon cc src\services\ingestion_service\app\DTOs\reference_data_dto.py -s`
  => `ClientTaxRuleSetRecord.validate_rule` `A (1)`, tax-rule evidence helper `B (6)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal DTO validator decomposition that preserves
public request contracts, OpenAPI schema names, and operator-facing documentation truth.
