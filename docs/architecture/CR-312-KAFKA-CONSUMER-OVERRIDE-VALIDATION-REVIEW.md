# CR-312 Kafka Consumer Override Validation Review

## Summary

`config.py` accepted some invalid Kafka consumer runtime overrides that only failed later at
consumer startup:

- invalid `auto.offset.reset` strings
- boolean values for integer settings like `max.poll.interval.ms`

## Why This Matters

This is shared config parsing across the platform. Letting invalid values pass through pushes
operator mistakes into later runtime startup failures instead of rejecting them at the config
boundary with clear validation behavior.

## Change

- added explicit allowed values for:
  - `auto.offset.reset`
- rejected boolean values for integer Kafka settings
- normalized valid `auto.offset.reset` strings to lowercase

## Evidence

- added direct unit proofs in:
  - `tests/unit/libs/portfolio-common/test_config.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_config.py -q`
    - `4 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/config.py tests/unit/libs/portfolio-common/test_config.py`
    - passed

## Follow-up

- if we want to go further, the next step is explicit minimum/maximum validation for selected
  integer Kafka settings. The main type-and-enum leak is now closed.
