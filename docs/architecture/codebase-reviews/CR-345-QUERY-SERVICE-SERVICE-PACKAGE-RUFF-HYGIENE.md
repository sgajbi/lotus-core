# CR-345 Query-Service Service Package Ruff Hygiene

Date: 2026-05-27

## Scope

Reviewed the full `src/services/query_service/app/services/` package after the operations
support-plane builder extractions.

## Findings

The touched builder slices passed Ruff, but a broader package sweep surfaced small existing hygiene
debt in neighboring query-service modules: unsorted imports and two overlong capability-service log
messages. This did not change runtime behavior, but it meant the service package could not be
validated cleanly as a whole.

## Actions Taken

Normalized import ordering in affected query-service modules and wrapped the overlong
capability-service warning messages without changing message semantics or behavior.

## Validation

Package-level validation:

```text
python -m ruff check src/services/query_service/app/services tests/unit/services/query_service/services
All checks passed

python -m pytest tests/unit/services/query_service/services -q
418 passed
```

## Follow-Up

No follow-up required for this hygiene scope. This is intentionally limited to formatting and
import-order cleanup discovered while validating the query-service service package.
