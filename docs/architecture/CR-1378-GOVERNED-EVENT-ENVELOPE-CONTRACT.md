# CR-1378 Governed Event Envelope Contract

Date: 2026-07-05

## Objective

Fix GitHub issue #552 by proving and documenting the governed event-envelope posture for event
family metadata, correlation, idempotency, schema versioning, source/evidence links, and unknown
field handling.

## Change

- Added a catalog-wide event supportability regression proving every active event family requires:
  - idempotency,
  - correlation,
  - schema versioning,
  - a source-data product or supportability evidence link.
- Preserved the existing event supportability catalog that classifies source ingestion, domain state,
  pipeline stage, reconciliation control, and supportability recovery event families.
- Corrected stale RFC-0083 gap-analysis wording so documentation matches current `CoreEventModel`
  behavior: governed envelope metadata is accepted and non-governed extra fields are rejected.

## Expected Improvement

Event metadata requirements are governed by a central catalog and test suite instead of remaining
implicit in individual optional DTO fields. Future event families cannot omit correlation,
schema-version, idempotency, or source/evidence posture without failing the validation tests.

## Tests Added Or Updated

- Updated `tests/unit/libs/portfolio-common/test_event_supportability.py` with
  `test_all_event_families_require_governed_envelope_metadata`.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_events.py tests/unit/libs/portfolio-common/test_event_mapping.py -q`
  - Result: passed.
- `python -m ruff check src/libs/portfolio-common/portfolio_common/event_supportability.py tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_events.py tests/unit/libs/portfolio-common/test_event_mapping.py`
  - Result: passed.
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/event_supportability.py tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_events.py tests/unit/libs/portfolio-common/test_event_mapping.py`
  - Result: passed.
- `make quality-wiki-docs-gate`
  - Result: passed.
- `make architecture-guard`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Compatibility

No event topic, existing schema field, persistence schema, public API, or runtime topology changed.
Existing valid event payloads remain compatible. Missing required metadata posture is governed at the
event-family catalog level, while unknown payload fields fail validation through `CoreEventModel`.

## Same-Pattern Scan

The event supportability catalog already covers source-ingestion, domain-state, pipeline-stage,
reconciliation-control, supportability-recovery, direct-Kafka, and supportability-surface families.
This slice adds an all-family metadata posture test and reuses the existing validation tests for
missing schema model bindings, missing schema versioning, missing direct-topic headers, source-data
product linkage, and operator-only supportability evidence.

## Documentation And Wiki Decision

Repository context, RFC-0083 gap-analysis wording, and the codebase review ledger are updated. No
wiki source change is required because no operator command, public API, or supported feature
description changed.

No platform skill change is required: the current backend/event governance guidance already covers
contract drift and support-safe evidence. The durable rule is repo-local event-envelope catalog
usage.
