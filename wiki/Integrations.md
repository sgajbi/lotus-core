# Integrations

Current scope: Core's source-owned integration surfaces and consumer boundaries. Analytics
content identity describes returned economic evidence; it does not certify a complete source cut
or downstream financial processing. Use the contract-specific evidence below when comparing reads.

| Reader | Start here | Decision boundary |
| --- | --- | --- |
| Analytics consumers | Analytics Content Identity | Compare returned pages without claiming a complete source cut. |
| Operators | Primary integration relationships | Identify the source owner before investigating missing evidence. |
| Engineers | Main integration surfaces | Select the supported contract without duplicating downstream calculations. |

## Primary integration relationships

- `lotus-gateway`
  workspace and product-facing composition over governed operational-read, snapshot, readiness, and
  source-data contracts
- `lotus-performance`
  canonical analytics-input, benchmark/reference, FX, and portfolio context sourcing
- `lotus-risk`
  canonical analytics-input, benchmark/reference, risk-free, and policy-aware snapshot sourcing
- `lotus-advise`
  stateful context reads, instrument and price support, and canonical advisory simulation execution
- `lotus-manage`
  management-side workflows that need core authority or future operator evidence adoption
- `lotus-report`
  reporting and evidence workflows that depend on governed core truth, even where current direct
  route adoption is intentionally narrow
- operator tooling and QA flows
  readiness, support, lineage, replay, and reconciliation investigation

## Main integration surfaces

- operational reads from `query_service`
- analytics-input, snapshot, policy, and support contracts from `query_control_plane_service`
- write-ingress contracts from `ingestion_service`
- replay and operations control-plane contracts from `event_replay_service`
- reconciliation control execution contracts

## Analytics Content Identity

`PortfolioTimeseriesInput` and `PositionTimeseriesInput` publish a deterministic `content_hash`
(also exposed as `source_digest`) over the actual returned economic rows, normalized request
basis, product and quality status. Equivalent Decimal scale and signed zero normalize without
rounding; dates and row ordering are deterministic. Serving timestamps and correlation IDs are
not economic revisions. Valuation, dated FX or cashflow corrections that change returned rows
change their content identity even when the request fingerprint and selected epoch are unchanged.

Projected dimension order/duplicates and effective dimension-filter value order/duplicates do not
change economic identity. Filters preserve exact values and existing last-key-wins semantics;
changed final values, value whitespace/case and different dimension membership remain significant.
Cursor request identity remains unchanged; returned economic row multiplicity is preserved.

Position economic identity uses normalized distinct security/position selector membership, matching
the repository's SQL inclusion filters: equivalent selector order, duplicates and security-ID
whitespace do not represent economic revisions. An absent filter (all rows) remains distinct from
a supplied filter with no valid members (no rows). Cursor/request fingerprints retain their
existing order-sensitive compatibility; other request basis and response-row multiplicity remain
bound to content identity.

`source_lineage.content_identity_scope` is `response_page`. Each page has its own digest;
`source_lineage.source_cut_status` remains `UNAVAILABLE` and `source_cut_id` remains null. Do not
compare page digests as whole-window revisions, concatenate them into an official source cut, or
infer cross-page snapshot isolation or upstream provider authority. Paging retains its existing
request/cursor semantics and partial-quality posture. Missing required FX still refuses the read;
an empty successful row set has a real content digest, not proof of financial completion.

Consumers retain their independent input/calculation identity and must inspect quality and cut
availability separately. This does not alter request fingerprints, certify historical snapshot
retention, or close the broader source-cut, FX-lineage and retained-export evidence obligations.
Implementation and regression evidence are in the
[content identity helper](https://github.com/sgajbi/lotus-core/blob/main/src/services/query_control_plane_service/app/application/analytics/analytics_content_identity.py)
and the
[PostgreSQL/HTTP correction tests](https://github.com/sgajbi/lotus-core/blob/main/tests/integration/services/query_control_plane_service/test_analytics_content_identity_postgresql.py).

## Surface Selection

Downstream consumers should use the correct family surface rather than treating `lotus-core` as one
undifferentiated API.

That means:

- use `query_service` for canonical operational reads
- use `query_control_plane_service` for policy, snapshot, analytics-input, support, lineage, and
  simulation-oriented source contracts
- use `ingestion_service` for write ingress
- use `event_replay_service` and `financial_reconciliation_service` for control execution and
  operations recovery, not for front-office reads

## Adoption rule

Do not overstate current direct adoption from this page.

Some Lotus applications consume `lotus-core` directly, some consume through `lotus-gateway`, and
some have catalog-intended future adoption without a broad active route footprint today.

When route-specific adoption matters, use the RFC-0082 contract-family inventory and downstream
consumer audit instead of treating this page as a route-by-route source of truth.

## Reference

- [RFC-0082 Contract Family Inventory](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0082-contract-family-inventory.md)
- [RFC-0082 Downstream Endpoint Consumer And Test Coverage Audit](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0082-downstream-endpoint-consumer-and-test-coverage-audit.md)
- [Architecture Index](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/README.md)
- [Query Service And Control Plane Boundary](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md)
- [API Surface](API-Surface)

## Read Next

1. use [API Surface](API-Surface) when you need the grouped route families rather than the repo map,
2. use [System Data Flow](System-Data-Flow) when the integration question depends on write-to-read materialization order,
3. use [Query Control Plane](Query-Control-Plane) when the change touches snapshot, analytics-input, support, lineage, or policy-bearing contracts.
