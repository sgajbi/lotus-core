# RFC 051 - Test Collection Reliability Hardening

## Problem Statement

Cross-repo pyramid measurement currently reports lotus-core `collect_errors` because:

- `tests/unit` and `tests/integration` import `openpyxl` but it is not listed in `tests/requirements.txt`.
- `tests/e2e/test_5_day_workflow.py` uses `@pytest.mark.dependency` while lotus-core runs with `--strict-markers`, and the `dependency` marker is not declared in pytest config.

This makes test inventory and governance telemetry noisy and unreliable.

## Root Cause

- Missing explicit dependency declaration for workbook-driven ingestion tests.
- Missing marker declaration for `pytest-dependency` usage under strict marker policy.

## Proposed Solution

- Add `openpyxl` to `tests/requirements.txt`.
- Add `"dependency: mark test dependency ordering/grouping"` to `tool.pytest.ini_options.markers` in `pyproject.toml`.

## Architectural Impact

No production runtime impact. This is test platform reliability hardening only.

## Risks and Trade-offs

- Adds one test dependency package (`openpyxl`) to test environment setup time.
- No behavioral impact on service code paths.

## High-Level Implementation

1. Update test dependency manifest.
2. Update pytest marker registry.
3. Re-run collection for unit/integration/e2e buckets.
4. Re-run PPD pyramid measurement to confirm lotus-core collection errors are resolved.
