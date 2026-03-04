# RFC 067 - Active Query Contract Governance and Vocabulary Policy

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-05 |
| Last Updated | 2026-03-05 |
| Owners | lotus-core query-service maintainers |
| Depends On | RFC 057, RFC 063, RFC-0067 governance |
| Scope | Active contract families and vocabulary controls for lotus-core query-service |

## Executive Summary
This RFC supersedes the outdated review-centric governance framing from RFC-034.
It defines the active, enforceable governance model for query-service contracts:
1. Contract ownership by active route families only.
2. Vocabulary governance through RFC-0067 inventory and no-alias policy.
3. OpenAPI quality gate and inventory validation as CI controls.

## Governed Contract Families
1. Integration contracts (`/integration/*`)
2. Analytics input contracts (`/integration/portfolios/{portfolio_id}/analytics/*`)
3. Simulation contracts (`/simulations/*`)
4. Support and lineage operations (`/operations/*`)
5. Lookup/catalog contracts (`/lookup/*`)

## Governance Rules
1. No legacy review/performance/risk/reporting endpoints in lotus-core query-service.
2. New fields must use canonical vocabulary terms and documented descriptions.
3. No response aliasing that diverges from canonical DTO field names.
4. OpenAPI quality gate must pass for every contract change.
5. API vocabulary inventory validation must pass for every contract change.

## Required CI Controls
1. `scripts/openapi_quality_gate.py`
2. `scripts/api_vocabulary_inventory.py --validate-only`
3. `scripts/no_alias_contract_guard.py`

## Evidence
1. `scripts/openapi_quality_gate.py`
2. `scripts/api_vocabulary_inventory.py`
3. `scripts/no_alias_contract_guard.py`
4. `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json`
5. `.github/workflows/ci.yml`

## Success Criteria
1. Any contract change that violates OpenAPI quality or vocabulary governance fails CI.
2. Legacy contract families remain absent from active query-service OpenAPI.
3. Active endpoint families remain documented and test-covered.
