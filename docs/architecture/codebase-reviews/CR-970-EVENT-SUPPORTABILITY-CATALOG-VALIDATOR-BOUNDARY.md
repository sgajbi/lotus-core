# CR-970: Event Supportability Catalog Validator Boundary

Date: 2026-06-05

## Scope

Split the shared event supportability catalog validator into focused helper boundaries without
changing catalog entries, schema-model validation, source-data product validation, supportability
surface validation, direct Kafka topic validation, dormant-event handling, or exception messages.

## Finding

`validate_event_supportability_catalog` mixed event-family validation, duplicate detection,
schema-model binding checks, source-data product checks, supportability surface checks, operator
security-profile checks, and direct Kafka topic checks in one E-ranked function. This made the
RFC-0083 event supportability contract harder to review and less suitable as a reusable shared
library guardrail.

## Action

Added focused private validators for available schema models, unique-name recording, event
definitions, governance flags, source/evidence links, evidence bundles, source-data products,
supportability surfaces, direct Kafka topics, and direct-topic header requirements. The public
`validate_event_supportability_catalog` API remains the orchestration entry point.

## Result

`validate_event_supportability_catalog` improved from `E (39)` to `A (5)`. The extracted helper
functions all report A-ranked cyclomatic complexity, and `event_supportability.py` remains
A-ranked maintainability at `A (26.87)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_event_supportability.py -q`
  => 19 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\event_supportability.py tests\unit\libs\portfolio-common\test_event_supportability.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\event_supportability.py tests\unit\libs\portfolio-common\test_event_supportability.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\event_supportability.py -s`
  => `validate_event_supportability_catalog` `A (5)`; all helper functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\event_supportability.py -s`
  => `event_supportability.py` `A (26.87)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\event_supportability.py`
  => 720 SLOC / 207 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared-library validator refactor that
preserves public API contracts, RFC-0083 catalog semantics, and operator-facing documentation truth.
