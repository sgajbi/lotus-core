# CR-390: FX Validation Control-Code Normalization

Date: 2026-05-28

## Scope

FX canonical transaction validation in `portfolio_common.transaction_domain`.

## Finding

FX validation still compared several source-controlled vocabulary fields using raw or
`upper()`-only values. Padded lower-case values such as ` fx_forward `,
` fx_contract_open `, ` quote_per_base `, ` buy `, ` none `, or
` upstream_provided ` could raise invalid validation findings even when the economic event was
otherwise canonical and deterministic.

The same issue also affected swap-specific validation branches, where padded lower-case
` fx_swap ` values could bypass the swap group-structure checks.

## Change

Reused the shared transaction-domain control-code normalizer inside `validate_fx_transaction(...)`
for FX business type, component type, quote convention, cash-leg role, spot exposure model, and
realized-PnL mode checks. Updated direct FX validation tests to prove padded lower-case values are
accepted for valid canonical events and still drive the expected swap structure validation branch.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_fx_validation.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/fx_validation.py tests/unit/libs/portfolio_common/test_fx_validation.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain FX canonical-validation reliability slice.
