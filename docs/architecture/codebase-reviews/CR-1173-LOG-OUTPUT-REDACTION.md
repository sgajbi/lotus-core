# CR-1173 Log Output Redaction

## Objective

Fix GitHub issue #496 locally by adding a shared redaction layer for structured logs and CI/test
console output.

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
- Removed raw Pydantic validation tracebacks from the persistence-consumer rejection path. Rejected
  messages now emit bounded error count, schema locations, error types, reason code and correlation
  identity without input values, serialized bodies or validator messages.
- Applied the same bounded validation evidence at the outer shared Kafka terminal-failure boundary,
  so rethrowing to DLQ recovery cannot emit a second raw traceback.
- Extended the shared formatter backstop to quoted, non-string, escaped and truncated mapping
  values, with compound and punctuated sensitive-key parity and harmless diagnostic fields
  retained.
- Restored fail-closed sensitive-token containment for arbitrary concatenated credential keys while
  retaining only explicit harmless diagnostic-key exceptions.
- Bounded malformed broker-payload redaction to the retained 16,384-character evidence prefix and
  reused the result for the durable excerpt, avoiding duplicate unbounded poison-record scans.

## Compatibility

No product API, OpenAPI route, database schema, Kafka payload, support API response, or downstream
business contract changed. Log and test-output values change intentionally when sensitive keys or
credential-bearing URL values are present.

## Validation

- Focused shared-consumer, persistence, logging and output-control pack: 245 passed.
- Repository-pinned Ruff lint/format, maintainability, source-size, structured-log, observability,
  MyPy and documentation/wiki guards: passed after the final edit.
- `make security-audit`
- Result: passed; dependency consistency was clean and `pip-audit` reported no known
  vulnerabilities, with expected local editable Lotus package PyPI skips.

## Documentation And Wiki Decision

Updated this ledger entry, repository context, security guidance, observability contract pack and
wiki security source. No operator command, API, schema or deployment topology changed.

## Follow-Up

The rejected-input residual in issue #496 is fixed locally pending PR, exact-main validation and
independent QA. Broader direct script-output scanning remains separate. DLQ and durable
replay/payload storage redaction remain owned by their existing issue-backed slices, including
CR-1174 and CR-1176.
