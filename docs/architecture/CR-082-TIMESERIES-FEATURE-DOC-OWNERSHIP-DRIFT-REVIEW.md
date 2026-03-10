# CR-082 Timeseries Feature Doc Ownership Drift Review

## Scope
- `docs/features/timeseries_generator/01_Feature_Timeseries_Generator_Overview.md`
- `docs/features/timeseries_generator/03_Methodology_Guide.md`
- `docs/features/timeseries_generator/05_Developer_Guide.md`

## Finding
The feature docs still described `timeseries_generator_service` as owning both:

- position-level time-series generation
- portfolio-level time-series aggregation

That stopped being true after the split to `portfolio_aggregation_service`. The operations guide had already been corrected earlier, but the overview, methodology, and developer guides were still describing the old ownership boundary.

## Change
Updated the feature documentation set to reflect the live split:

- `timeseries_generator_service` owns position-timeseries generation
- `portfolio_aggregation_service` owns portfolio-timeseries aggregation and scheduler-driven claim logic

Also corrected the developer-guide file paths and test paths so contributors are sent to the live portfolio-aggregation sources instead of the removed pre-split locations.

## Why this is the right fix
- current-state docs now match current-state code
- contributor guidance no longer points to deleted or mis-owned files
- no runtime behavior changed

## Residual follow-up
- The `timeseries_generator` feature-doc directory still groups both stages under one topic. That is acceptable for now because it documents one end-to-end capability, but if the split grows further, separate feature directories may become cleaner.

## Evidence
- `docs/features/timeseries_generator/01_Feature_Timeseries_Generator_Overview.md`
- `docs/features/timeseries_generator/03_Methodology_Guide.md`
- `docs/features/timeseries_generator/05_Developer_Guide.md`
