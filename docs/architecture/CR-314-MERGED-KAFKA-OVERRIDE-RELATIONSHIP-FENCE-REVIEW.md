# CR-314 Merged Kafka Override Relationship Fence Review

## Summary

`CR-313` validated Kafka consumer override relationships inside each source map, but the final
merged result could still create an invalid combination across layers.

Example:

- defaults: `session.timeout.ms = 30000`
- group override: `heartbeat.interval.ms = 30000`

Each source map looked valid in isolation, but the merged result still violated
`heartbeat.interval.ms < session.timeout.ms`.

## Why This Matters

This is exactly the kind of config bug that slips through “validated inputs” and then fails later
at runtime because the bad combination only appears after layering.

## Change

- added final merged-boundary relationship validation in:
  - `get_kafka_consumer_runtime_overrides(group_id)`

## Evidence

- expanded direct unit proofs in:
  - `tests/unit/libs/portfolio-common/test_config.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_config.py -q`
    - `8 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/config.py tests/unit/libs/portfolio-common/test_config.py`
    - passed

## Follow-up

- no immediate follow-up here. The important fix is that relationship validation now applies at the
  same merged boundary the runtime actually consumes.
