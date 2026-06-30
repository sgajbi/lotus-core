# CR-1173 Log Output Redaction

## Objective

Begin GitHub issue #496 by adding a shared redaction layer for structured logs and CI/test console
output.

## Expected Improvement

- Structured JSON logs use a shared redacting formatter.
- Enterprise audit redaction uses the same shared policy instead of carrying a local duplicate.
- Test/CI console output masks database URL credentials and inline authorization/token/secret-like
  values before printing.
- Internal database URL construction can still use full credentials when needed for SQLAlchemy
  connectivity, but the shared output path redacts before emission.

## Changes

- Added `redact_sensitive(...)`, `redact_sensitive_text(...)`, and `RedactingJsonFormatter` to
  `portfolio_common.logging_utils`.
- Switched `setup_logging()` to the redacting JSON formatter.
- Reused the shared redaction function from `portfolio_common.enterprise_readiness`.
- Routed `tests.test_support.output_control.emit_test_output(...)` through
  `redact_sensitive_text(...)`.
- Added focused tests for nested structured redaction, database URL credential masking, JSON
  formatter masking, and test-output masking.

## Compatibility

No product API, OpenAPI route, database schema, Kafka payload, support API response, or downstream
business contract changed. Log and test-output values change intentionally when sensitive keys or
credential-bearing URL values are present.

## Validation

- `python -m pytest tests/unit/libs/portfolio-common/test_logging_utils.py tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py::test_redact_sensitive_masks_nested_values tests/unit/test_support/test_output_control.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/logging_utils.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py tests/test_support/output_control.py tests/unit/libs/portfolio-common/test_logging_utils.py tests/unit/test_support/test_output_control.py`
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/logging_utils.py src/libs/portfolio-common/portfolio_common/enterprise_readiness.py tests/test_support/output_control.py tests/unit/libs/portfolio-common/test_logging_utils.py tests/unit/test_support/test_output_control.py`

## Documentation And Wiki Decision

Updated this ledger entry and the quality scorecard/health report. No wiki source change is
required because this is an internal logging and test-output hardening slice with no operator
command change.

## Follow-Up

Issue #496 remains open pending PR, GitHub CI, and QA evidence. Broader follow-up should extend the
redaction policy to DLQ/replay payload storage and add static checks for direct secret-bearing
console output in scripts.
