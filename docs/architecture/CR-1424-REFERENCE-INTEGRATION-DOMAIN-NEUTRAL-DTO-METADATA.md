# CR-1424 Reference Integration Domain-Neutral DTO Metadata

## Status

Fixed-local candidate on 2026-07-06.

## Scope

Reference integration DTO metadata and DPM portfolio-universe boundary wording for GitHub issue
#539.

## Finding

`reference_integration_dto.py` included downstream application names and downstream workflow wording
in field descriptions/examples. The most material cases were the `lotus-manage` benchmark source
example, `include_policy_pack` being justified by one consumer, discretionary authority being
described as consumer-specific behavior, and the DPM portfolio-universe boundary naming downstream
campaign, ranking, execution-readiness, client-communication workflow, and external workflow
ownership.

That made Core's source-data contracts appear tailored to a consuming application instead of
publishing domain-neutral private-banking source contracts.

## Action

Reworded the affected DTO descriptions/examples to use source-data, mandate-policy, portfolio
management, request-context, and source-authority vocabulary. Updated the emitted DPM
portfolio-universe boundary string to match the neutral authority language. Added a DTO metadata
regression test that scans `reference_integration_dto.py` model metadata for forbidden downstream
Lotus app names and the specific downstream-owned boundary phrases.

## Compatibility

No field names, enum values, request validation behavior, route paths, repository reads, pagination,
source metadata, OpenAPI schema structure, or runtime ownership changed. One response string value
for `DpmPortfolioUniverseCandidateSelectionBasis.downstream_boundary` intentionally changed to the
domain-neutral equivalent.

## No Wiki Change

No repo wiki update is required for this slice. The change corrects OpenAPI/DTO metadata and one
source-boundary explanatory response value; no operator workflow, API route, or published runbook
changed.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\dtos\test_reference_integration_dto.py tests\unit\services\query_service\services\test_dpm_portfolio_universe.py tests\unit\services\query_service\services\test_integration_service.py -q
python -m ruff check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\services\dpm_portfolio_universe.py tests\unit\services\query_service\dtos\test_reference_integration_dto.py tests\unit\services\query_service\services\test_dpm_portfolio_universe.py tests\unit\services\query_service\services\test_integration_service.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\services\dpm_portfolio_universe.py tests\unit\services\query_service\dtos\test_reference_integration_dto.py tests\unit\services\query_service\services\test_dpm_portfolio_universe.py tests\unit\services\query_service\services\test_integration_service.py
python -m mypy src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\services\dpm_portfolio_universe.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
