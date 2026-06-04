# CR-882 FX Linkage Complexity Gate

Date: 2026-06-04

## Scope

Remove the final source complexity blocker from the current Xenon threshold and promote the broad
source complexity check into an enforced quality-baseline gate.

## Finding

After CR-880 and CR-881, repository-wide Xenon no longer reported F-ranked blocks, but
`src/libs/portfolio-common/portfolio_common/transaction_domain/fx_linkage.py` still reported a
D-ranked module because `enrich_fx_transaction_metadata` held all FX event linkage decisions in one
function.

That made FX contract, swap, cash-leg, and instrument-routing policy harder to review and prevented
truthful broad complexity enforcement.

## Action

Split `enrich_fx_transaction_metadata` into small pure helpers for:

1. FX business transaction detection,
2. economic event and linked group id defaults,
3. swap event, near-leg, and far-leg grouping,
4. FX contract id derivation,
5. FX cash-leg role derivation,
6. FX contract instrument/security routing,
7. contract open/close transaction id derivation.

Added the repo-native `make quality-complexity-gate` target and a dedicated
`Quality Baseline / Complexity Gate` workflow job that runs:

```powershell
python -m xenon --max-absolute E --max-modules C --max-average A src
```

## Result

`enrich_fx_transaction_metadata` now reports `B (7)` under Radon, and repository-wide Xenon passes
under the current threshold. The broad complexity baseline is now enforceable instead of
report-only.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_fx_linkage.py -q` => `5 passed`
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py -s`
  => `enrich_fx_transaction_metadata - B (7)`
- `make quality-complexity-gate` => clean
- `.github/workflows/quality-baseline.yml` includes `complexity-gate`

## Wiki Decision

No wiki source update is required for this slice. The change is an internal transaction-domain
maintainability refactor plus quality-gate promotion; it does not change operator-facing runtime
behavior, API surface, onboarding flow, or wiki-owned product truth.

