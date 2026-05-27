# CR-349 Reference Data Helper Boundary Review

Date: 2026-05-27

## Scope

Reviewed deterministic reference-data helper logic inside `IntegrationService`.

## Findings

`IntegrationService` still embedded reusable reference-data transformations alongside repository
orchestration and source-data product response assembly. The embedded helpers selected latest
effective records, resolved composition windows, classified market reference quality, and found the
latest durable evidence timestamp.

These transformations are pure business rules and should be directly testable without constructing
the full integration service.

## Actions Taken

Extracted deterministic reference-data helper behavior into
`src/services/query_service/app/services/reference_data_helpers.py`.

`IntegrationService` keeps compatibility wrappers for current call sites and delegates:

1. latest durable reference evidence timestamp selection,
2. market reference quality classification,
3. latest effective record selection by business key,
4. component window resolution with inferred superseded end dates.

Added direct unit tests for the helper module covering quality classification, durable evidence
timestamp selection, latest-record selection, and component-window end-date inference.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/query_service/services/test_reference_data_helpers.py tests/unit/services/query_service/services/test_integration_service.py -q
97 passed

python -m ruff check src/services/query_service/app/services/integration_service.py src/services/query_service/app/services/reference_data_helpers.py tests/unit/services/query_service/services/test_reference_data_helpers.py tests/unit/services/query_service/services/test_integration_service.py
All checks passed
```

## Follow-Up

No API or wiki source change is required for this slice because source-data contracts and public
response shape did not change. Continue splitting `IntegrationService` around cohesive source-data
product groups where repository orchestration and DTO construction can be separated cleanly.
