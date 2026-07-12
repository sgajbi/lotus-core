# CR-1303 Shared Domain Value Objects

## Scope

Issue cluster: GitHub issue #660.

This slice introduces a narrow shared private-banking value-object standard and applies it to a
representative reporting-currency conversion path.

## Objective

Define framework-free executable value objects for currency, money, FX rate, quantity, price, and
currency basis semantics, then use them in a calculation path that previously passed raw `Decimal`
amounts and string currency pairs through service code.

## Changes

1. Added `portfolio_common.domain_value_objects` with:
   - `CurrencyCode`;
   - `MoneyAmount`;
   - `FxRate`;
   - `CurrencyBasis`;
   - `Quantity`;
   - `UnitPrice`;
   - named monetary aliases for book cost, market value, accrued income, withholding tax, and
     realized P&L.
2. Rewired query-service FX conversion to normalize money and currency through the shared value
   objects while keeping the existing async converter signature and returned `Decimal` values.
3. Rewired transaction reporting-currency conversion to use `CurrencyBasis`, `MoneyAmount`, and
   normalized boundary currency values before invoking the existing converter.
4. Added direct value-object tests for equality, rounding/quantization, boundary serialization,
   missing/null handling, same-currency FX identity, cross-currency conversion, non-positive FX
   rejection, and currency-basis mismatch protection.

## Behavior And Compatibility

This is a domain-standard and representative-use slice inside existing deployables.

No route path, request DTO, response DTO, OpenAPI metadata, repository method signature, FX lookup
query, cache key semantics, returned `Decimal` value, reporting-currency field name, pagination
behavior, or converter callable signature changed.

## Validation Evidence

Focused local validation before docs update:

1. `python -m pytest tests\unit\libs\portfolio-common\test_domain_value_objects.py tests\unit\services\query_service\services\test_transaction_reporting_currency.py tests\unit\services\query_service\services\test_fx_conversion.py -q`
   - 15 passed.
2. `python -m pytest tests\unit\services\query_service\services\test_transaction_records.py tests\unit\services\query_service\services\test_transaction_service.py -q`
   - 32 passed.

Final scoped lint, format, docs, and diff evidence is recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger and repo-local engineering context.

No wiki update is required because this slice changes internal implementation standards and
representative service internals, not operator commands, route behavior, supported features, or
published wiki truth.

No central Lotus skill change is required. The repeatable pattern is repo-local: calculation paths
should normalize API/ORM primitives into framework-free value objects at the boundary and serialize
back to primitives only at API, event, or persistence edges.

## Remaining Work

GitHub issue #660 is locally fixed for the representative value-object acceptance criteria pending
PR CI/QA and issue closure. Future slices should migrate reconciliation money/price evidence, tax
totals, cash balances, and cost-engine models to the same value-object pattern instead of creating
parallel primitives.
