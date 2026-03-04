# RFC 015 - Hyper-Personalization via Client Profile Enrichment

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-08-30 |
| Last Updated | 2026-03-04 |
| Owners | Advisory intelligence/reporting domains (outside lotus-core) |
| Depends On | RFC 011, RFC 009 |
| Scope | Archived from `lotus-core`; partially related data-model asks not implemented here |

## Executive Summary

RFC 015 proposed enriching portfolio records with deep `client_profile` semantics for personalized NBA and narrative reporting.
In lotus-core, this RFC was not implemented as specified and its principal consumers (`nba-service`, `insight-report-service`) are out of current core scope.

## Original Requested Requirements (Preserved)

Original RFC 015 requested:
1. Add `client_profile` JSONB-style enrichment to portfolio data model.
2. Extend ingestion/persistence/query paths to accept/store/serve this profile.
3. Enable NBA and insight engines to use profile context for personalized signals and narratives.
4. Introduce richer goal/preference/constraint-aware recommendation behaviors.

## Current Implementation Reality

1. No `client_profile` field exists on lotus-core `Portfolio` model in current schema.
2. Ingestion portfolio DTO does not carry client-profile block.
3. Persistence portfolio repository/event model does not process that profile.
4. Primary downstream AI services referenced by RFC are outside lotus-core ownership.

Evidence:
- `src/libs/portfolio-common/portfolio_common/database_models.py` (`Portfolio` model)
- `src/services/ingestion_service/app/DTOs/portfolio_dto.py`
- `src/libs/portfolio-common/portfolio_common/events.py` (`PortfolioEvent`)
- `src/services/persistence_service/app/repositories/portfolio_repository.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Add `client_profile` on portfolio schema | Not implemented | portfolio DB model |
| Ingest and persist client profile | Not implemented | portfolio DTO/event/repository |
| Expose enriched profile via query APIs | Not implemented in current contract | query DTO/service surfaces |
| Use in NBA/insight engines | Out of lotus-core runtime scope | cross-app ownership context |

## Design Reasoning and Trade-offs

1. **Why archive here**: RFC value is tied to advisor-intelligence services not owned by lotus-core.
2. **Core trade-off**: keeping lotus-core lean on canonical financial data reduces coupling to rapidly changing personalization semantics.
3. **Potential future path**: if profile becomes a canonical upstream master-data requirement, reintroduce via a dedicated core contract RFC with clear ownership.

## Gap Assessment

No immediate lotus-core implementation gap is tracked under current ownership model.
This RFC is best treated as out-of-scope for core until a cross-app governance decision makes client-profile canonical in core data contracts.

## Deviations and Evolution Since Original RFC

1. NBA/insight service roadmap did not materialize inside lotus-core boundary.
2. Lotus-core model evolution focused on canonical processing/integration contracts, not personalization intelligence.

## Proposed Changes

1. Keep RFC 015 archived in lotus-core.
2. If reactivated, reframe as cross-repo master-data contract RFC with explicit owners and downstream adopters.

## Test and Validation Evidence

1. Absence evidence in model/DTO/event/repository paths listed above.

## Original Acceptance Criteria Alignment

Original acceptance criteria are not met in lotus-core by design because scope is outside current repository ownership.

## Rollout and Backward Compatibility

No runtime change from this documentation retrofit.

## Open Questions

1. Should client-profile semantics become canonical enterprise master data (and if yes, which repo owns the canonical schema)?

## Next Actions

1. Keep this RFC archived as historical context.
2. Re-home active profile-enrichment roadmap to the recommendation/reporting domain repositories.
