# CR-997: Kafka Topic Verification Boundary

Date: 2026-06-05

## Scope

Split required Kafka topic verification into admin-client construction, metadata lookup,
missing-topic calculation, and verification helpers without changing retry behavior, bootstrap
server selection, missing-topic `KafkaException` behavior, unexpected-error wrapping, or consumer
manager startup semantics.

## Finding

`ensure_topics_exist` mixed retry-decorated orchestration, admin client construction, cluster
metadata retrieval, existing-topic extraction, missing-topic calculation, missing-topic exception
creation, success logging, Kafka exception retry logging, and unexpected-error wrapping in one
B-ranked helper. This made shared Kafka runtime support harder to review.

## Action

Added focused helpers for admin-client construction, required-topic verification, existing-topic
metadata lookup, and missing-topic calculation while keeping the public retry-decorated function as
the orchestration boundary.

## Result

`ensure_topics_exist` improved from `B (6)` to `A (3)`. All functions/classes in
`kafka_admin.py` now report A-ranked cyclomatic complexity, and the module remains A-ranked
maintainability at `A (88.15)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_kafka_admin.py -q`
  => 3 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\kafka_admin.py tests\unit\libs\portfolio-common\test_kafka_admin.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\kafka_admin.py tests\unit\libs\portfolio-common\test_kafka_admin.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\kafka_admin.py -s`
  => `ensure_topics_exist` `A (3)` and all functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\kafka_admin.py -s`
  => `kafka_admin.py` `A (88.15)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\kafka_admin.py`
  => 38 SLOC / 35 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal Kafka runtime helper refactor that preserves
topic verification and retry semantics.
