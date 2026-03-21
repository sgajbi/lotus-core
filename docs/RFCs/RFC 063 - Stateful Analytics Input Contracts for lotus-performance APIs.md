# RFC 063 - Stateful Analytics Input Contracts for lotus-performance APIs

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-01 |
| Last Updated | 2026-03-21 |
| Owners | lotus-core integration query owners; lotus-performance consumers |
| Depends On | RFC 058, RFC 062, RFC-0067 |
| Related Standards | API vocabulary governance; rounding and precision standards |
| Scope | Cross-repo |

## Executive Summary
RFC 063 defines high-volume stateful analytics input contracts for lotus-performance. The core endpoint family is implemented: portfolio timeseries, position timeseries, analytics reference metadata, and async export job lifecycle endpoints.

The implemented shape aligns closely with the RFC goals, including deterministic paging, lineage metadata, and separation of enrichment responsibilities.

## Original Requested Requirements (Preserved)
1. Provide dedicated portfolio and position analytics timeseries input contracts.
2. Keep enrichment non-redundant (separate enrichment contract usage).
3. Add async export job contracts for large dataset retrieval.
4. Support deterministic paging/chunking and stream-friendly retrieval patterns.
5. Preserve strict ownership boundary (lotus-core inputs, lotus-performance analytics).

## Current Implementation Reality
1. `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` implemented.
2. `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` implemented.
3. `POST /integration/portfolios/{portfolio_id}/analytics/reference` implemented.
4. Export job lifecycle endpoints (`create`, `status`, `result`) implemented.
5. Integration tests and router dependency tests validate request/response and export retrieval behavior.

## Position-Timeseries Contract Baseline
This RFC now treats `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` as a hardened stateful contract, not just a convenient raw input feed.

### Request contract
1. Exactly one of `window` or `period` must be supplied.
2. `include_cash_flows` defaults to `true`.
3. `consumer_system`, paging, dimension filters, and requested dimensions are part of the deterministic request scope.

### Response contract
1. `*_position_currency` values are expressed in the native position currency.
2. `*_portfolio_currency` values are expressed in the portfolio base currency, even for non-base-currency positions.
3. `*_reporting_currency` values are always populated for the effective reporting currency and no longer rely on null-as-same-currency semantics.
4. Each row carries:
   - `position_to_portfolio_fx_rate`
   - `portfolio_to_reporting_fx_rate`
   - `cash_flow_currency`
5. Paging metadata is explicit and self-describing:
   - `page_size`
   - `returned_row_count`
   - `sort_key`
   - `request_scope_fingerprint`
   - `snapshot_epoch`
   - `next_page_token`
6. Diagnostics explicitly declare:
   - requested dimensions
   - whether cash flows were included

### Why this matters
These changes close three important gaps:
1. non-base positions no longer masquerade as portfolio-currency values
2. downstream consumers no longer need implicit knowledge to know whether cash-flow semantics are present
3. pagination is auditable and replay-safe

## Portfolio-Timeseries Contract Baseline
The portfolio companion endpoint now has a stronger contract baseline as well.

### Request contract
1. Exactly one of `window` or `period` must be supplied.
2. `reporting_currency` determines the value and cash-flow currency of returned observations.
3. Paging is deterministic and snapshot-pinned.

### Response contract
1. `PortfolioTimeseriesObservation.beginning_market_value` and `ending_market_value` are always expressed in the effective `reporting_currency`.
2. `PortfolioTimeseriesObservation.cash_flows` are canonical portfolio-level performance flows in that same reporting currency.
3. Each observation includes `cash_flow_currency` so consumers do not need to infer flow-currency semantics.
4. Portfolio diagnostics are endpoint-specific and include:
   - `expected_business_dates_count`
   - `returned_observation_dates_count`
   - `missing_dates_count`
   - `stale_points_count`
   - `cash_flows_included`

### Why this matters
This endpoint feeds stateful TWR and MWR. The contract now states clearly:
1. what currency the totals are in
2. what business-calendar completeness means
3. whether the consumer is looking at a fully covered or partially missing portfolio window

## Analytics-Reference Contract Baseline
`POST /integration/portfolios/{portfolio_id}/analytics/reference` is now treated as an explicit
reference contract rather than a vague metadata helper.

### Request contract
1. `as_of_date` is required.
2. `consumer_system` is part of the governed request context.

### Response contract
1. `resolved_as_of_date` is echoed explicitly.
2. `performance_end_date` is bounded by `resolved_as_of_date`.
3. `reference_state_policy` explicitly states that portfolio reference fields come from the
   current canonical portfolio record.
4. `supported_grouping_dimensions` declares the canonical analytics grouping dimensions without
   overloading the payload as historical taxonomy state.

### Why this matters
This endpoint no longer implies historical effective-dated portfolio metadata it cannot actually
provide. The contract is now explicit about two separate truths:
1. portfolio reference fields are current canonical portfolio state
2. performance horizon metadata is bounded by the requested as-of date

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Portfolio timeseries input endpoint | Implemented | `src/services/query_control_plane_service/app/routers/analytics_inputs.py`; `tests/integration/services/query_service/test_analytics_inputs_router_dependency.py` |
| Position timeseries input endpoint | Implemented | same router/service path |
| Analytics reference metadata endpoint | Implemented | `analytics_inputs.py` |
| Async export create/status/result endpoints | Implemented | `analytics_inputs.py` (`/exports/analytics-timeseries/jobs*`) |
| Deterministic error mapping and contract behavior | Implemented | `analytics_inputs.py` + router dependency tests |
| Ownership separation and enrichment reuse model | Implemented in contract design | analytics router descriptions + enrichment endpoint retained in integration router |

## Design Reasoning and Trade-offs
1. Dedicated timeseries endpoints reduce overloading of snapshot endpoints for long-horizon analytics acquisition.
2. Async export contracts improve reliability for large extraction windows.
3. Keeping enrichment out of bulk timeseries rows avoids payload bloat and duplication.

## Gap Assessment
1. The position-timeseries contract required additional hardening beyond the original rollout:
   - strict request-shape validation
   - explicit paging semantics
   - corrected portfolio/reporting currency behavior for non-base positions
   - safer cash-flow defaulting for downstream attribution/contribution consumers
2. Ongoing performance tuning and stream-format operational validation should continue as non-functional hardening.

## Deviations and Evolution Since Original RFC
1. RFC text is "proposed" language while major contract surfaces are implemented.
2. Implementation adds practical error and export lifecycle handling details consistent with production needs.
3. Position-timeseries semantics were strengthened after initial rollout to remove ambiguous currency labeling and silent cash-flow omission defaults.

## Proposed Changes
1. Rebaseline RFC 063 status/narrative to implemented baseline.
2. Keep performance-scale hardening under RFC 065/066 operational gates.

## Test and Validation Evidence
1. `src/services/query_control_plane_service/app/routers/analytics_inputs.py`
2. `tests/integration/services/query_service/test_analytics_inputs_router_dependency.py`
3. `src/services/query_service/app/services/analytics_timeseries_service.py`

## Original Acceptance Criteria Alignment
1. New timeseries contracts present and usable: aligned.
2. Async export lifecycle available: aligned.
3. Ownership and non-redundant enrichment model: aligned.

## Rollout and Backward Compatibility
1. The position-timeseries hardening includes intentional breaking contract changes:
   - `include_cash_flows` now defaults to `true`
   - reporting-currency fields are always populated for the effective reporting currency
   - portfolio-currency values for non-base positions now reflect true portfolio-currency conversion rather than mirroring position-currency values
2. Downstream consumers must align to the corrected semantics rather than rely on legacy interpretation.

## Open Questions
1. Should explicit cross-consumer conformance suites be added for lotus-performance historical windows with large-page and ndjson result checks?

## Next Actions
1. Maintain analytics input contract and export job tests in CI.
2. Continue load-profile validation through RFC-066 gates for large-window requests.
3. Keep `lotus-performance` aligned with the corrected position-timeseries currency and paging semantics.
