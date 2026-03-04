# RFC 051 - Test Collection Reliability Hardening

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | test infrastructure reliability |
| Depends On | pytest strict-marker policy |
| Scope | Eliminate test collection errors impacting governance telemetry |

## Executive Summary

RFC 051 is implemented.
Both root causes identified in the RFC are resolved:
1. `openpyxl` is present in test requirements.
2. `dependency` marker is declared in pytest configuration while strict markers remain enabled.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC requested:
1. Add missing `openpyxl` dependency to test environment.
2. Register `dependency` marker under strict-marker enforcement.
3. Restore reliable test collection behavior for governance/telemetry flows.

## Current Implementation Reality

Implemented:
1. `tests/requirements.txt` includes `openpyxl==3.1.5`.
2. `pyproject.toml` includes marker declaration:
   - `"dependency: mark test dependency ordering/grouping"`.
3. `--strict-markers` remains enabled, meaning marker usage is now explicit and collection-safe.

Evidence:
- `tests/requirements.txt`
- `pyproject.toml`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Add workbook dependency | Implemented | `tests/requirements.txt` |
| Declare `dependency` marker | Implemented | `pyproject.toml` pytest markers |
| Improve collection reliability | Implemented by configuration closure of both identified causes | requirements + pytest config |

## Design Reasoning and Trade-offs

1. Explicit dependency and marker declaration reduces non-deterministic CI collection failures.
2. Maintaining strict markers preserves test hygiene while avoiding false negatives from missing registration.

Trade-off:
- Slightly larger test environment dependency footprint.

## Gap Assessment

No high-value implementation gap identified for RFC 051 scope.

## Deviations and Evolution Since Original RFC

1. None material; implementation matches proposal directly.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.

## Test and Validation Evidence

1. `tests/requirements.txt`
2. `pyproject.toml`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for RFC 051 scope.

## Next Actions

1. Keep dependency/marker declarations synchronized with future test framework additions.
