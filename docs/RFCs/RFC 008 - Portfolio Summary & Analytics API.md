# RFC 008 - Portfolio Summary and Analytics API

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-08-30 |
| Last Updated | 2026-03-04 |
| Owners | lotus-report (authoritative owner for summary/reporting API) |
| Depends On | RFC 056, RFC 057 |
| Related Standards | `docs/standards/data-model-ownership.md` |
| Scope | Archived from `lotus-core`; endpoint ownership moved to `lotus-report` |

## Executive Summary

RFC 008 originally proposed a consolidated `POST /portfolios/{portfolio_id}/summary` API in lotus-core query service.
That endpoint ownership has moved to lotus-report.

Important prerequisite data-model parts from RFC 008 were implemented in lotus-core (instrument enrichment fields), so this RFC remains relevant as design lineage even though API ownership moved.

## Original Requested Requirements (Preserved)

Original RFC 008 requested:
1. New consolidated summary endpoint with sections (`WEALTH`, `PNL`, `INCOME`, `ACTIVITY`, `ALLOCATION`).
2. Epoch-safe reads for summary calculations.
3. Instrument model enrichment for allocation dimensions (`asset_class`, `sector`, `country_of_risk`, `rating`, `maturity_date`).
4. Support for “Unclassified” allocation grouping when enrichment data is missing.
5. Additional transaction/cost handling refinements in calculator layers to align summary correctness.

## Current Implementation Reality

1. Summary/reporting endpoint ownership moved out of lotus-core to lotus-report; lotus-core returns migration guidance (`410 Gone`).
2. Instrument enrichment portion is implemented in lotus-core schema and ingestion/persistence contracts.
3. Some transactional refinement asks in RFC 008 are superseded by other RFC waves and actual engine behavior.

Evidence:
- `docs/RFCs/RFC 056 - Remove Legacy Query Analytics and Reporting Endpoints.md`
- `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md`
- `tests/e2e/test_summary_pipeline.py`
- `tests/e2e/test_complex_portfolio_lifecycle.py`
- `alembic/versions/6acc877cf070_feat_add_asset_allocation_fields_to_.py`
- `src/services/ingestion_service/app/DTOs/instrument_dto.py`
- `src/libs/portfolio-common/portfolio_common/events.py`
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `src/services/persistence_service/app/repositories/instrument_repository.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Serve summary endpoint from lotus-core | De-owned; endpoint migrated to lotus-report | RFC 056; summary e2e 410 tests |
| Epoch-safe summary reads in lotus-core | No longer applicable in-core (endpoint moved) | ownership change docs/tests |
| Instrument enrichment fields | Implemented in schema + DTO/event + persistence | migration + DTO/event/repo files |
| Unclassified grouping behavior in summary API | Applies to lotus-report-owned endpoint now | ownership change |
| Transaction/cost refinement asks under summary scope | Partially implemented via broader transaction RFCs; not owned by summary endpoint now | transaction engine code and later RFCs |

## Design Reasoning and Trade-offs

1. **Why de-own summary API**: reporting orchestration belongs with report-focused service boundary.
2. **Why keep enrichment in lotus-core**: canonical instrument/reference data remains core platform responsibility.
3. **Trade-off**: cross-service migration complexity, but clearer long-term ownership and less duplicated reporting logic.

## Gap Assessment

No lotus-core implementation gap remains for the summary endpoint itself.
Relevant remaining core value is maintaining high-quality canonical input data for downstream report services.

## Deviations and Evolution Since Original RFC

1. API surface de-owned under RFC 056/057.
2. Instrument enrichment survived and became useful beyond summary API (core snapshot/analytics inputs).
3. Some calculation refinement asks were absorbed into transaction RFC stream rather than this reporting RFC.

## Proposed Changes

1. Keep RFC 008 archived with full rationale and implementation lineage.
2. Maintain enrichment data quality in lotus-core.
3. Keep endpoint-level summary/report evolution in lotus-report.

## Test and Validation Evidence

1. Summary endpoint migration behavior:
   - `tests/e2e/test_summary_pipeline.py`
   - `tests/e2e/test_complex_portfolio_lifecycle.py`
2. Enrichment model support:
   - `alembic/versions/6acc877cf070_feat_add_asset_allocation_fields_to_.py`
   - `instrument_dto.py`, `events.py`, `database_models.py`, `instrument_repository.py`

## Original Acceptance Criteria Alignment

1. Instrument enrichment acceptance is satisfied in lotus-core.
2. Summary endpoint acceptance moved to lotus-report ownership.
3. Lotus-core acceptance is now compatibility/migration behavior plus input-data contract support.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should lotus-core maintain a formal data-quality metric specifically for enrichment completeness consumed by lotus-report?

## Next Actions

1. Keep archived pointer in lotus-core.
2. Keep summary/reporting API ownership in lotus-report.
3. Continue instrument enrichment quality and contract stability in lotus-core.
