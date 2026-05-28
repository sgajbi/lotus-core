# CR-348 Request Fingerprint Boundary Review

Date: 2026-05-27

## Scope

Reviewed request and time-series fingerprint construction inside `IntegrationService`.

## Findings

`IntegrationService` still owned deterministic source-data request fingerprinting directly beside
product orchestration, pagination, repository calls, and DTO assembly. The fingerprinting behavior is
small, but it is contract-sensitive because downstream source-data responses use it for snapshot
identity, page-token scope binding, lineage, and repeatable evidence.

The embedded implementation also kept the non-cryptographic hash decision local to the service
monolith instead of making it an explicit reusable utility boundary.

## Actions Taken

Extracted deterministic request fingerprint behavior into
`src/services/query_service/app/services/request_fingerprint.py`.

`IntegrationService` now keeps compatibility wrappers for current call sites and delegates:

1. generic request payload fingerprinting to `request_fingerprint(...)`,
2. series request fingerprint construction to `series_request_fingerprint(...)`.

Added direct unit tests proving stable key-order handling, payload-value sensitivity, and series
fingerprint scope changes when extra request dimensions are supplied.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/query_service/services/test_request_fingerprint.py tests/unit/services/query_service/services/test_integration_service.py -q
96 passed

python -m ruff check src/services/query_service/app/services/integration_service.py src/services/query_service/app/services/request_fingerprint.py tests/unit/services/query_service/services/test_request_fingerprint.py tests/unit/services/query_service/services/test_integration_service.py
All checks passed
```

## Follow-Up

No API or wiki source change is required for this slice because request fingerprints remain an
internal deterministic contract and public response shape did not change. Continue decomposing
`IntegrationService` around source-data product families and deterministic reference-data helpers.
