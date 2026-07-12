# CR-1413 Benchmark Reference Integration Family

## Status

In progress on 2026-07-06.

## Scope

`IntegrationService` benchmark, index, risk-free, coverage, and classification reference products
in `query_service`.

## Finding

GitHub issue #548 remains valid: `IntegrationService` still carried the benchmark/reference
source-data product family as direct facade methods. The actual response assembly and quality
policy already lived in focused resolver modules, but the facade still owned reference-repository
access and page-token wiring for benchmark assignment, benchmark definition, benchmark composition,
benchmark catalog, index catalog, benchmark market series, index series, benchmark return series,
risk-free series, coverage reports, and classification taxonomy.

That kept market-reference product orchestration coupled to unrelated integration dependencies and
made future benchmark/reference changes harder to test without the full facade.

## Action

Added `BenchmarkReferenceIntegrationService` as the benchmark/reference contract-family boundary.
The family service owns reference-repository provider access and benchmark market-series page-token
adapter wiring while delegating to the existing resolver modules.

`IntegrationService` now constructs the family service from its existing dependency bundle and keeps
the public facade methods as thin compatibility delegates.

## Compatibility

No downstream API contract changes are intended in this slice. Existing route handlers and service
callers continue to use the same facade methods and DTO contracts. Benchmark assignment metadata,
benchmark definition/component mapping, benchmark market-series paging, index/risk-free
normalization, coverage fingerprints, classification taxonomy response shape, supportability,
lineage, data-quality status, source-data product names, repository SQL, and runtime topology are
unchanged.

## Remaining Issue Scope

This is a partial issue #548 slice. Additional contract-family extractions are still needed before
the issue should be marked fixed-local, including client profile/income products and remaining DPM
portfolio-management reference products.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_integration_service.py tests\unit\services\query_service\services\test_risk_free_series.py tests\unit\services\query_service\services\test_risk_free_coverage.py -q
python -m ruff check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\benchmark_reference_integration_service.py tests\unit\services\query_service\services\test_integration_service.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\benchmark_reference_integration_service.py tests\unit\services\query_service\services\test_integration_service.py
python -m mypy src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\benchmark_reference_integration_service.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
