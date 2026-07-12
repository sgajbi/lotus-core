# CR-383: FX Contract Instrument Control-Code Normalization

Date: 2026-05-28

## Scope

FX contract synthetic instrument construction in `portfolio_common.transaction_domain`.

## Finding

FX contract instrument construction uppercased component and currency control codes without
trimming source values. Padded lower-case values such as ` fx_contract_open `, ` usd `, or ` eur `
could:

1. skip synthetic FX contract instrument creation for valid open or close components,
2. preserve padded currency values on generated instrument records,
3. degrade downstream FX contract identity and analytics inputs.

This mattered because FX contract instruments are generated from transaction components and reused
by calculator and query paths as canonical instrument metadata.

## Change

Added local control-code normalization for FX contract component and buy/sell currency checks.
Updated direct tests to prove padded lower-case component and currency values still produce the
expected synthetic instrument and that non-contract cash-settlement components remain excluded.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_fx_contract_instrument.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/fx_contract_instrument.py tests/unit/libs/portfolio_common/test_fx_contract_instrument.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain control-code normalization slice for reliable FX contract instrument generation.
