# CR-104: Dead Timeseries Scheduler Residue Review

## Scope

- `timeseries_generator_service` dead scheduler residue after the RFC 81 split

## Finding

After the `portfolio_aggregation_service` split, `AggregationScheduler` is owned by the portfolio aggregation runtime. A dead copy still remained under `timeseries_generator_service` together with a worker-local unit test. The dead copy was not imported by production code, so it created the wrong ownership signal and an unnecessary maintenance surface.

## Action taken

- Deleted the dead scheduler copy from `timeseries_generator_service`
- Deleted the dead worker-local unit test for that copy
- Updated current-state feature docs so they correctly state that:
  - `portfolio_aggregation_service` owns the aggregation scheduler
  - `timeseries_generator_service` consumes aggregation work but does not schedule it

## Why this is correct

The worker service should not carry dormant scheduling code after ownership has moved. Leaving the file in place increases the risk of future fixes landing in the wrong service and blurs the operational model established by RFC 81.

## Evidence

- Deleted:
  - `src/services/timeseries_generator_service/app/core/aggregation_scheduler.py`
  - `tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_aggregation_scheduler.py`
- Updated:
  - `docs/features/timeseries_generator/02_API_Specification_Timeseries_Generator.md`
  - `docs/features/timeseries_generator/04_Operations_Troubleshooting_Guide.md`
