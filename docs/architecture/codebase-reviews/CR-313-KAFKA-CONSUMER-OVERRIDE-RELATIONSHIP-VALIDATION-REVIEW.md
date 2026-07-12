# CR-313 Kafka Consumer Override Relationship Validation Review

## Summary

After `CR-312`, shared config parsing still accepted some impossible or unsafe Kafka consumer
override relationships, including:

- non-positive millisecond settings
- `heartbeat.interval.ms >= session.timeout.ms`

These values only failed later at consumer startup.

## Why This Matters

This is shared config parsing across the platform. Invalid cross-field relationships should be
rejected at the config boundary instead of surfacing later as less precise Kafka startup failures.

## Change

- required positive integers for selected Kafka consumer settings
- added shared relationship validation for:
  - `heartbeat.interval.ms < session.timeout.ms`
- invalid heartbeat/session relationships now drop the heartbeat override and keep the valid
  session timeout

## Evidence

- expanded direct unit proofs in:
  - `tests/unit/libs/portfolio-common/test_config.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_config.py -q`
    - `7 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/config.py tests/unit/libs/portfolio-common/test_config.py`
    - passed

## Follow-up

- if we want to go further, the next step is validating additional Kafka override relationships
  against known broker/client constraints. The highest-value type and timing relationship gap is
  now closed.
