# CR-152 - Replay Duplicate Normalization Observability Review

## Scope
- `reprocessing_job_repository` duplicate normalization
- replay durable queue observability
- Grafana replay dashboard coverage

## Finding
Replay duplicate normalization had become a meaningful runtime control, but it was only visible through logs and tests. Operators could not see whether the system was actively collapsing historical duplicate `RESET_WATERMARKS` rows under pressure.

## Fix
- Added `reprocessing_duplicates_normalized_total{scope=...}` to the shared monitoring layer.
- Emitted the metric from `normalize_pending_reset_watermarks_duplicates()`.
- Added a Grafana panel for the normalization rate.

## Result
Replay duplicate cleanup is now observable as a first-class operational signal instead of a log-only side effect.
