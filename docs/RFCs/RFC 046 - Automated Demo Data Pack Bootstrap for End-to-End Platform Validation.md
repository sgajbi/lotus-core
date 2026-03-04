# RFC 046 - Automated Demo Data Pack Bootstrap for End-to-End Platform Validation

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-05 |
| Owners | `lotus-core` platform bootstrap tooling |
| Depends On | RFC 035, RFC 036, RFC 045 |
| Scope | Automated compose-time demo dataset ingest and verification workflow |

## Executive Summary

RFC 046 proposed automated demo data bootstrap for deterministic local/platform validation.
Major implementation is in place:
1. `tools/demo_data_pack.py` exists and builds + ingests + verifies multi-portfolio data.
2. `docker-compose.yml` includes one-shot `demo_data_loader` integrated into startup flow.
3. Operations docs include runbook guidance.

Remaining gap is governance/documentation-only:
1. RFC numbering/scope collision with explorer RFC under the same `046` identifier remains open.

Classification: `Partially implemented (requires enhancement)`.

## Original Requested Requirements (Preserved)

Original RFC 046 requested:
1. Deterministic, realistic multi-portfolio demo data pack.
2. Compose-time bootstrap automation using canonical ingestion/query APIs.
3. Verification loop proving downstream processing readiness.
4. Test coverage and operational documentation.

## Current Implementation Reality

Implemented:
1. Demo bundle builder produces portfolios, instruments, transactions, prices, FX rates, and business dates.
2. CLI workflow supports ingest/verify modes, readiness waits, polling, and idempotency checks.
3. Compose `demo_data_loader` service runs bootstrap automatically and supports enable/disable flag.
4. Troubleshooting docs describe usage and failure diagnosis.

Resolved in this loop:
1. `tests/integration/tools/test_demo_data_pack.py` is aligned to current schema/semantics and passes.

Open:
1. Numbering/scope governance (`RFC-046-D02`) due duplicate RFC identifier usage.

Evidence:
- `tools/demo_data_pack.py`
- `docker-compose.yml` (`demo_data_loader`)
- `docs/features/core_data_ingestion/04_Operations_Troubleshooting_Guide.md`
- `tests/integration/tools/test_demo_data_pack.py`
- Local execution: `.\.venv\Scripts\python.exe -m pytest -q tests/integration/tools/test_demo_data_pack.py` (`3 passed` on 2026-03-05)

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Deterministic demo pack artifact | Implemented | `tools/demo_data_pack.py` |
| Compose-time one-shot bootstrap | Implemented | `docker-compose.yml` `demo_data_loader` |
| Readiness + verification loop | Implemented | readiness wait + `_verify_portfolio` logic |
| Test and docs coverage | Implemented for bootstrap contract tests; governance collision remains | troubleshooting guide + passing integration test |

## Design Reasoning and Trade-offs

1. Using canonical ingestion/query APIs for demo bootstrapping validates real integration paths.
2. One-shot loader keeps local startup repeatable and operator-friendly.

Trade-off:
- Rich demo verification logic requires disciplined test maintenance; stale tests can hide real drift or create false failure noise.

## Gap Assessment

Remaining delta:
1. Resolve RFC numbering/scope collision and ownership map (`RFC-046-D02`).
2. Ensure demo-data suite remains in enforced CI paths for ongoing drift detection.

## Deviations and Evolution Since Original RFC

1. Delivery scope expanded with robust verification heuristics and force-ingest controls.
2. Test drift was corrected and suite now reflects current contract behavior.

## Proposed Changes

1. Keep classification as `Partially implemented` until `RFC-046-D02` governance closure.
2. Maintain demo-data test contract alignment in CI.

## Test and Validation Evidence

1. Implementation artifact:
   - `tools/demo_data_pack.py`
2. Compose integration:
   - `docker-compose.yml`
3. Current test evidence:
   - `tests/integration/tools/test_demo_data_pack.py`
   - `.\.venv\Scripts\python.exe -m pytest -q tests/integration/tools/test_demo_data_pack.py`

## Original Acceptance Criteria Alignment

Partially aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should demo data pack verification be required in default CI, or retained as optional integration gate due runtime cost?

## Next Actions

1. Close `RFC-046-D02` (numbering/scope governance).
2. Confirm CI gate placement for the demo-data suite.

