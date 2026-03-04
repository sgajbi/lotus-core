# RFC 045 - Lotus Core Ingestion Healthcheck Reliability and Runtime Readiness

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | `ingestion-service`, platform run reliability |
| Depends On | Docker compose runtime contract |
| Scope | Eliminate false unhealthy status for ingestion service readiness in compose environments |

## Executive Summary

RFC 045 addressed a concrete container healthcheck reliability defect.
The core problem is resolved:
1. Ingestion healthcheck now uses a Python urllib probe instead of `curl`.
2. Readiness endpoint health is checked directly in-container without missing-tool failures.
3. Startup orchestration paths that depend on healthy ingestion status are aligned with this fix.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 045 requested:
1. Replace ingestion probe dependence on unavailable `curl`.
2. Improve runtime readiness fidelity.
3. Strengthen startup/smoke reliability around health-driven orchestration.

## Current Implementation Reality

Implemented:
1. `ingestion_service` healthcheck in compose uses:
   - `python -c "import urllib.request; urllib.request.urlopen(.../health/ready...)"`.
2. `demo_data_loader` and downstream readiness choreography depend on healthy services, including ingestion.
3. Operational troubleshooting docs include demo-loader and readiness troubleshooting guidance.

Evidence:
- `docker-compose.yml` (`ingestion_service.healthcheck`)
- `docker-compose.yml` (`demo_data_loader` depends-on healthy services)
- `tools/demo_data_pack.py` readiness wait logic
- `docs/features/core_data_ingestion/04_Operations_Troubleshooting_Guide.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Remove missing-tool healthcheck dependency | Implemented | `docker-compose.yml` ingestion healthcheck command |
| Reliable readiness semantics | Implemented for ingestion runtime path | readiness probe + loader dependency chain |
| Health-aware startup confidence | Implemented with one-shot loader and readiness wait/poll tooling | compose + `demo_data_pack.py` |

## Design Reasoning and Trade-offs

1. Probe command must use tooling guaranteed present in image runtime.
2. Readiness-based gating is more meaningful for integration startup than process-up checks alone.

Trade-off:
- Different services still use mixed probe styles (`curl` vs `python`), so operational style is not fully uniform across all containers.

## Gap Assessment

No blocking implementation gap for the ingestion-specific defect this RFC targeted.

## Deviations and Evolution Since Original RFC

1. The practical fix focused on ingestion reliability; full cross-service healthcheck style standardization remains optional follow-on hygiene.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.

## Test and Validation Evidence

1. Compose-based readiness orchestration paths:
   - `docker-compose.yml`
2. Runtime readiness wait implementation:
   - `tools/demo_data_pack.py`

## Original Acceptance Criteria Alignment

Aligned for ingestion-service reliability objective.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should lotus-core standardize all service healthchecks to a single probe style in a separate ops RFC?

## Next Actions

1. Keep ingestion health probe behavior stable and monitor compose startup reliability trends.
