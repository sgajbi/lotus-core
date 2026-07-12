# CR-386: FX Baseline Realized-PnL Mode Normalization

Date: 2026-05-28

## Scope

FX baseline processed-event construction in `portfolio_common.transaction_domain`.

## Finding

FX baseline processing uppercased `fx_realized_pnl_mode` without trimming source values and did
not write the canonical mode back to the processed event. A padded lower-case ` none ` value could
miss the `NONE` branch and preserve upstream realized PnL values that should have been zeroed under
baseline processing semantics.

This mattered because FX processed events feed downstream validation, calculator, and query paths
that rely on explicit realized-PnL treatment.

## Change

Added local control-code normalization for `fx_realized_pnl_mode` and wrote the canonical mode onto
the processed event. Added direct tests proving padded lower-case `none` zeros realized PnL and
padded lower-case `upstream_provided` preserves provided realized PnL totals with canonical mode
metadata.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_fx_baseline_processing.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/fx_baseline_processing.py tests/unit/libs/portfolio_common/test_fx_baseline_processing.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain calculation reliability slice for deterministic FX realized-PnL baseline
processing.
