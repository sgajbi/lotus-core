# CR-959: Reference Data Tax DTO Family Boundary

Date: 2026-06-05

## Scope

Move client tax profile and client tax rule-set DTO records plus their ingestion request wrappers
into a dedicated reference-data tax DTO module without changing request fields, validation
semantics, schema names, router imports, or public compatibility imports from `reference_data_dto.py`.

## Finding

`reference_data_dto.py` remained a large C-ranked maintainability hotspot after CR-958. The client
tax profile and tax rule-set records were cohesive private-banking tax contracts, but they still
lived inline with unrelated reference-data DTO families and ingestion request wrappers.

## Action

Added `reference_data_tax_dto.py` to own:

- `ClientTaxProfileRecord`
- `ClientTaxRuleSetRecord`
- `ClientTaxProfileIngestionRequest`
- `ClientTaxRuleSetIngestionRequest`
- tax rule effective-window, threshold-pair, and bounded-evidence validators

Kept explicit compatibility re-exports from `reference_data_dto.py` so existing routers, tests,
OpenAPI schema names, and downstream imports continue to resolve through the original module.

## Result

`reference_data_dto.py` shrank from 1,686 SLOC to 1,511 SLOC and improved from `C (0.00)` to
`C (1.05)` under Radon maintainability. The extracted tax DTO module reports `A (29.60)`
maintainability. `reference_data_dto.py` remains an active C-ranked hotspot because additional
client preference, instrument eligibility, and model-portfolio DTO families still live inline.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\test_reference_data_dto.py -q`
  => 35 passed
- `python -m ruff check src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py tests\unit\services\ingestion_service\test_reference_data_dto.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py tests\unit\services\ingestion_service\test_reference_data_dto.py`
  => 3 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py`
  => `reference_data_dto.py` 1,511 SLOC; `reference_data_tax_dto.py` 190 SLOC
- `python -m radon mi src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py -s`
  => `reference_data_dto.py` `C (1.05)`; `reference_data_tax_dto.py` `A (29.60)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal DTO module boundary extraction that preserves
public request contracts, OpenAPI schema names, router behavior, and operator-facing documentation
truth.
