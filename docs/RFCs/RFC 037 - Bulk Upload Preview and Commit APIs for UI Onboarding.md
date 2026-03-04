# RFC 037 - Bulk Upload Preview and Commit APIs for UI Onboarding

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | `ingestion-service` |
| Depends On | RFC 035 phase-1 onboarding patterns, RFC 057 adapter-mode governance |
| Scope | File-based onboarding via preview/commit APIs reusing canonical DTO validation |

## Executive Summary

RFC 037 is implemented in lotus-core with production-grade behavior:
1. `POST /ingest/uploads/preview` validates CSV/XLSX rows and returns row-level diagnostics without publishing.
2. `POST /ingest/uploads/commit` validates and publishes to canonical topics with strict/partial modes.
3. Adapter-mode guards, write controls, and integration tests are in place.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 037 requested:
1. File preview API with row-level validation feedback.
2. Commit API with strict default and optional partial publish mode.
3. Reuse existing DTO/event contracts to avoid ingestion path drift.
4. Support core entities (`portfolios`, `instruments`, `transactions`, `market_prices`, `fx_rates`, `business_dates`).

## Current Implementation Reality

Implemented:
1. Upload preview and commit endpoints are present in ingestion-service router.
2. Parser supports `.csv` and `.xlsx`; invalid format/content returns deterministic `400`.
3. Header normalization maps common case/alias variants to canonical model fields.
4. Validation uses existing DTO models; commit publishes only valid normalized records.
5. `allow_partial=false` path rejects mixed-validity files (`422`), while `allow_partial=true` publishes valid rows and reports skipped rows.
6. Adapter-mode feature flags can disable upload APIs with explicit `410` response contracts.
7. Rate-limit and write-mode checks are applied on commit path.

Evidence:
- `src/services/ingestion_service/app/routers/uploads.py`
- `src/services/ingestion_service/app/services/upload_ingestion_service.py`
- `src/services/ingestion_service/app/adapter_mode.py`
- `tests/unit/services/ingestion_service/services/test_upload_ingestion_service.py`
- `tests/integration/services/ingestion_service/test_ingestion_routers.py`
- `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Preview endpoint with row-level errors | Implemented | uploads router + upload service |
| Commit endpoint with strict/partial behavior | Implemented | upload service + ingestion router tests |
| DTO validation reuse | Implemented through model-driven validation map by entity type | upload service model mapping |
| Supported entities coverage | Implemented for all listed entity types | upload DTO/service + tests |
| Deterministic error reporting | Implemented with row number and validation issue details | upload service + integration tests |

## Design Reasoning and Trade-offs

1. Reusing canonical DTO validation keeps JSON and file ingestion semantics aligned.
2. Preview-before-commit pattern reduces production ingestion noise and manual correction time.
3. Adapter-mode gating keeps this convenient API explicitly non-canonical for upstream production pipelines.

Trade-off:
- File parsing adds complexity and dependency footprint (`openpyxl`) that must remain test-hardened.

## Gap Assessment

No high-value implementation gap identified for RFC 037 scope.

## Deviations and Evolution Since Original RFC

1. Adapter-mode controls were strengthened and explicitly documented in runtime error contracts.
2. Runtime ingestion write/rate controls are integrated on commit path.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.
2. Continue treating upload APIs as adapter-mode onboarding capability rather than primary canonical ingestion channel.

## Test and Validation Evidence

1. Upload service unit tests:
   - `tests/unit/services/ingestion_service/services/test_upload_ingestion_service.py`
2. End-to-end router behavior tests:
   - `tests/integration/services/ingestion_service/test_ingestion_routers.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Preview and commit flows are implemented with requested semantics.
2. Entity coverage and validation behavior match RFC intent.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for RFC 037 baseline scope.

## Next Actions

1. Maintain parser/validation regression tests as DTO schemas evolve.
