# lotus-core Supported Features

## Current Supported Capability Families

`lotus-core` currently supports:

1. portfolio and instrument master data,
2. transaction ingestion and booking foundations,
3. position, valuation, cashflow, and time-series foundations,
4. operational read-plane query APIs,
5. governed query-control-plane source-data products,
6. ingestion and persistence support surfaces,
7. reconciliation, supportability, lineage, and operational evidence APIs,
8. DPM and front-office source-data product support where declared in repository contracts,
9. performance-facing component economics evidence where declared as
   `PerformanceComponentEconomics:v1`.

Canonical supported-feature truth is maintained in
`contracts/supported-features/lotus-core-supported-features.v1.json` and validated by:

```powershell
make supported-features-guard
```

The guard checks that this document and `wiki/Supported-Features.md` carry the manifest-backed
capability names, status values, evidence links, fail-closed limitations, and downstream ownership
caveats.

## Manifest-Backed Capability Status

| Capability | Manifest status | Owner | Publication boundary |
| --- | --- | --- | --- |
| Portfolio and account source of record | `supported` | `lotus-core` | Source truth only; downstream apps own analytics and product experience. |
| Transaction and booking evidence | `supported` | `lotus-core` | Booking and ledger evidence only; tax advice, execution, and reporting interpretation are downstream-owned. |
| Position, valuation, and cashflow calculators | `supported` | `lotus-core` | Source-data foundations only; performance, risk, advice, and liquidity conclusions are downstream-owned. |
| Operational read plane | `supported` | `lotus-core` | Operational reads must not drift into report composition, advice, risk, or performance ownership. |
| Query control plane | `supported` | `lotus-core` | Source-data products and control-plane evidence only; consumer adoption proof remains downstream-owned. |
| DPM source-data products | `supported_with_fail_closed_dependencies` | `lotus-core` | Core publishes source readiness and fail-closed external dependency posture; DPM decisions remain `lotus-manage` owned. |
| Market/reference products | `supported` | `lotus-core` | Coverage and reference evidence only; attribution and risk conclusions remain downstream-owned. |
| Ingestion and replay | `supported` | `lotus-core` | Operational ingestion, replay, DLQ, and recovery evidence only; downstream semantic outcomes remain consumer-owned. |
| Reconciliation and supportability | `supported` | `lotus-core` | Operator evidence only unless a route family explicitly supports product use. |
| Simulation and advisory source effects | `producer_certified_downstream_owned` | `lotus-core` | Deterministic source-effect evidence only; advisory decisioning remains `lotus-advise` owned. |

## Supported Surface Families

The app-level validation command treats these implementation-backed surface families as the current
Core support map:

1. Portfolio and account source of record
2. Transaction and booking evidence
3. Position, valuation, and cashflow calculators
4. Operational read plane
5. Query control plane
6. Performance and DPM source-data products
7. Ingestion and replay
8. Reconciliation and supportability
9. Simulation and advisory source effects

## Boundary Statement

Supported features must be implementation-backed. This document should not be used to claim
capabilities that are only planned, mocked, or fail-closed pending external bank-owned data
ingestion.

## Evidence Sources

1. `REPOSITORY-ENGINEERING-CONTEXT.md`
2. `docs/standards/route-contract-family-registry.json`
3. `docs/architecture/CODEBASE-REVIEW-LEDGER.md`
4. `docs/methodologies/source-data-products/`
5. `contracts/domain-data-products/`
6. `make lotus-core-validate`, which runs app-level supported-surface validation, seeds
   deterministic synthetic data through the runtime smoke path, calls real Core APIs and
   calculations, checks contract/doc truth, writes JSON evidence under
   `output/lotus-core-validation/`, and exits non-zero on weak proof.
7. `make docs-evidence-pack`, which writes `output/documentation-evidence/` with a release-ready
   manifest for README, wiki, API vocabulary, RFC ledger, supported-feature, and runbook evidence.
8. `contracts/supported-features/lotus-core-supported-features.v1.json`, guarded by
   `make supported-features-guard`, which maps every published capability to implementation
   modules, routes, source-data products, tests, validation evidence, safe demo claims, prohibited
   claims, limitations, and downstream ownership caveats.
