# CR-389: FX Linkage Control-Code Normalization

Date: 2026-05-28

## Scope

FX transaction linkage metadata enrichment in `portfolio_common.transaction_domain`.

## Finding

FX linkage enrichment uppercased transaction type and component type without trimming source
values. Padded lower-case values such as ` fx_forward `, ` fx_swap `,
` fx_cash_settlement_buy `, or ` fx_contract_close ` could:

1. skip FX metadata enrichment entirely,
2. miss swap group defaulting,
3. miss cash-leg role inference,
4. fail to route contract open/close components to the generated FX contract instrument identity.

The helper also preserved padded policy-mode values when callers supplied `spot_exposure_model` or
`fx_realized_pnl_mode`.

## Change

Reused the shared transaction-domain control-code normalizer for FX transaction type, component
type, spot exposure model, and realized-PnL mode enrichment. Updated direct FX linkage tests to
prove padded lower-case forwards, swaps, cash-settlement legs, and contract-close components still
receive deterministic linkage, policy, role, and instrument metadata.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_fx_linkage.py tests/unit/libs/portfolio_common/test_fx_contract_instrument.py tests/unit/libs/portfolio_common/test_fx_baseline_processing.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/fx_linkage.py tests/unit/libs/portfolio_common/test_fx_linkage.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain FX lineage, booking, and instrument-identity reliability slice.
