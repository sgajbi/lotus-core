# CR-181 Analytics Export Support Listing Review

## Finding

The support plane exposed queue health for analytics export jobs in the overview, but it did not expose the underlying durable job rows. That left operators without a first-class way to inspect failed, stuck, or repeated analytics export requests through the control plane.

## Change

- Added `AnalyticsExportJobRecord` and `AnalyticsExportJobListResponse`
- Added repository queries for analytics export job count and paged listing
- Added `OperationsService.get_analytics_export_jobs(...)`
- Added `GET /support/portfolios/{portfolio_id}/analytics-export-jobs`
- Added unit, integration, and OpenAPI contract coverage

## Why it matters

Support operators can now inspect durable analytics export jobs directly instead of inferring state from aggregate counters alone.
