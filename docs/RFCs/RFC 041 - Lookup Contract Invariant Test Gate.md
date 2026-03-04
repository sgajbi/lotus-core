# RFC 041 - Lookup Contract Invariant Test Gate

- Status: IMPLEMENTED
- Date: 2026-02-23
- Owners: lotus-core Query Service

## Context

Lookup APIs now power UI/lotus-gateway selector behavior. Regressions in item shape, sorting, search filtering, or source scoping can break UX and create subtle cross-service contract drift.

## Decision

Add a dedicated lotus-core integration test gate for lookup contract invariants:

- New test suite: `tests/integration/services/query_service/test_lookup_contract_router.py`
- Asserts:
  - canonical item shape (`id`, `label` non-empty strings)
  - deterministic sorting and limit behavior
  - case-insensitive query filtering
  - currency source scoping behavior (`source=INSTRUMENTS`) and uppercase normalization
- Wired into:
  - `make test-integration-lite`
  - CI integration-lite matrix args in `.github/workflows/ci.yml`

## Rationale

- Makes selector contract breakages explicit and fast to detect.
- Prevents accidental behavior drift during lotus-core API evolution.
- Keeps lotus-gateway/UI integrations stable without needing heavy end-to-end runs.

## Consequences

Positive:
- Stronger API contract confidence for lookup consumers.
- Lower risk of production UI selector regressions.

Trade-offs:
- Slightly longer integration-lite runtime.

## Follow-ups

- Extend invariant coverage to include future entitlement/tenant-aware lookup rules.
- Add contract snapshots if lookup payloads gain richer metadata.
