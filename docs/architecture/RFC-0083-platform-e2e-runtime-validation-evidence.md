# RFC-0083 Platform E2E Runtime Validation Evidence

- Status: Passed
- Date: 2026-04-15
- Scope: `lotus-core` RFC-0082/RFC-0083 downstream contract runtime proof
- Branch: `feat/rfc-0082-boundary-governance`
- Portfolio: `PB_SG_GLOBAL_BAL_001`
- Benchmark: `BMK_PB_GLOBAL_BALANCED_60_40`
- Governed as-of date: `2026-04-10`
- Validation owner: `lotus-workbench`
- Runtime contract: `canonical-front-office-demo-data-contract 1.0.0`
- Panel registry: `workbench-panel-registry 1.0.0`

## Purpose

This document records the platform end-to-end runtime proof for the `lotus-core` RFC-0082/RFC-0083
contract hardening program.

The target-model slices are already closed through guarded local artifacts. This evidence closes the
previous platform-validation gap for the canonical front-office path that depends on core source-data
products.

## Commands

Canonical stack bring-up:

```powershell
npm run live:stack:up
```

Canonical validation:

```powershell
npm run live:validate
```

The validation ran from `C:\Users\Sandeep\projects\lotus-workbench`.

## Runtime Evidence Summary

Generated evidence:

1. `C:\Users\Sandeep\projects\lotus-workbench\output\playwright\live-canonical\live-validation-summary.json`
2. `C:\Users\Sandeep\projects\lotus-workbench\output\playwright\live-canonical\SHOT-INDEX.md`
3. `C:\Users\Sandeep\projects\lotus-workbench\output\playwright\live-canonical\portfolio-summary-live.png`
4. `C:\Users\Sandeep\projects\lotus-workbench\output\playwright\live-canonical\portfolio-detailed-live.png`
5. `C:\Users\Sandeep\projects\lotus-workbench\output\playwright\live-canonical\performance-summary-live.png`
6. `C:\Users\Sandeep\projects\lotus-workbench\output\playwright\live-canonical\performance-analysis-live.png`
7. `C:\Users\Sandeep\projects\lotus-workbench\output\playwright\live-canonical\performance-advisor-brief-live.png`
8. `C:\Users\Sandeep\projects\lotus-workbench\output\playwright\live-canonical\performance-risk-live.png`
9. `C:\Users\Sandeep\projects\lotus-workbench\output\playwright\live-canonical\performance-evidence-live.png`

The final validation command passed with:

```text
Live canonical Workbench validation passed for PB_SG_GLOBAL_BAL_001.
```

## Routes Validated

The validation summary recorded HTTP 200 responses for:

| Consumer route | Purpose |
| --- | --- |
| `GET /api/v1/foundation/portfolios/PB_SG_GLOBAL_BAL_001/workspace` | Gateway foundation workspace backed by core source state |
| `GET /api/v1/workbench/PB_SG_GLOBAL_BAL_001/overview` | Gateway portfolio overview |
| `GET /api/v1/workbench/PB_SG_GLOBAL_BAL_001/performance/summary` | Performance summary through Gateway |
| `GET /api/v1/workbench/PB_SG_GLOBAL_BAL_001/performance/details` | Performance contribution and attribution detail through Gateway |
| `GET /api/v1/workbench/PB_SG_GLOBAL_BAL_001/performance/advisor-brief` | Advisor brief through Gateway |
| `GET /api/v1/workbench/PB_SG_GLOBAL_BAL_001/risk/summary` | Risk summary through Gateway |
| `GET /api/v1/workbench/PB_SG_GLOBAL_BAL_001/risk/concentration` | Risk concentration through Gateway |
| `GET /api/v1/workbench/PB_SG_GLOBAL_BAL_001/risk/drawdown` | Risk drawdown through Gateway |
| `GET /api/v1/workbench/PB_SG_GLOBAL_BAL_001/risk/rolling` | Rolling risk through Gateway |
| `GET /api/v1/workbench/PB_SG_GLOBAL_BAL_001/risk/attribution` | Historical risk attribution through Gateway |
| `GET /integration/capabilities` on `lotus-manage` | Manage integration capability posture |
| `GET /integration/capabilities` on `lotus-report` | Report integration capability posture |

## Calculation And Panel Evidence

The final validation summary recorded:

| Check | Evidence |
| --- | --- |
| Performance return path | 4 observation rows |
| Performance contribution | 4 contribution rows |
| Performance attribution | `supported`, 4 attribution rows |
| Risk summary | 7 ready metrics |
| Risk drawdown | 75 underwater-series rows |
| Risk rolling | 4 emitted windows, 2 computable latest-volatility windows |
| Historical risk attribution | 7 contributors |
| Portfolio summary | ready |
| Portfolio detailed | ready |
| Performance summary | ready |
| Performance analysis contribution | ready |
| Performance analysis attribution | ready |
| Performance advisor brief | ready |
| Performance risk panels | ready |
| Performance evidence | intentionally unavailable / truthfully degraded under RFC-0079 |

## Issues Found And Resolved During Validation

The live validation surfaced two governance/runtime drift issues:

1. The platform panel registry still classified `performance.analysis.attribution` as `partial`, but
   the live Gateway/Performance contract now returns supported attribution detail with populated rows.
   This was corrected in `lotus-platform`.
2. The Workbench live validator still expected older mode-tab semantics. The current Workbench uses
   left-rail mode buttons and a collapsed observation trail. The validator was updated in
   `lotus-workbench` to assert the current panel semantics while preserving row-count and
   supportability checks.

No additional `lotus-core` route, data, or persistence change was required for the final passing
validation run.

## Remaining Production Proof

This evidence closes the platform end-to-end validation gap for the canonical front-office flow.

The following proof remains outside this slice:

1. full `lotus-core` PR Merge Gate,
2. affected downstream consumer PR Merge Gates,
3. full gateway/platform authorization and entitlement proof when opt-in service-policy controls
   move to production enforcement,
4. full cross-service event replay proof when event payload behavior changes beyond the centrally
   guarded outbox envelope.
