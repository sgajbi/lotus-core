# CR-1304 Cost Engine Domain Model Independence

## Scope

Issue cluster: GitHub issue #657.

This slice separates cost-engine domain models from Pydantic framework concerns while preserving
existing cost-calculation behavior and internal engine compatibility.

## Objective

Make `Fees`, `Transaction`, and `ErroredTransaction` usable by the cost engine without importing
Pydantic from `cost_engine/domain`, and keep validation/coercion at the parser/adapter boundary.

## Changes

1. Replaced Pydantic `BaseModel` cost-engine domain models with pure Python dataclasses.
2. Kept compatibility helpers required by current engine and repository code:
   - `Transaction.model_copy(...)`;
   - `Transaction.model_dump(...)`;
   - `Fees.model_dump(...)`.
3. Rewired `TransactionParser` to construct domain transactions directly instead of using Pydantic
   `TypeAdapter`.
4. Added a focused guard test proving `cost_engine/domain` does not import Pydantic.
5. Added `docs/standards/cost-engine-domain-model-standard.md` to make the boundary rule explicit.

## Behavior And Compatibility

No route path, event payload, Kafka topic, database schema, repository method signature, persisted
transaction field, cost field, realized P&L field, fee-breakdown field, BUY-lot field, error list
shape, processing metric, sorter behavior, or cost-strategy result changed.

`model_copy(...)` intentionally preserves the existing non-revalidating copy behavior because some
legacy repair/replay tests mutate in-memory transaction values before strategy-level normalization.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\calculators\cost_calculator_service\engine tests\unit\services\calculators\cost_calculator_service\consumer\test_transaction_processor.py tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_repository.py -q`
   - 115 passed.
2. Scoped Ruff lint passed.
3. Scoped Ruff format passed.
4. `rg "pydantic" src\services\calculators\cost_calculator_service\app\cost_engine\domain -n`
   - no matches.

Final docs and diff evidence is recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger, repo-local engineering context, and the cost-engine domain-model
standard.

No wiki update is required because this slice changes internal domain layering and test guards, not
operator commands, route behavior, supported features, or published wiki truth.

No central Lotus skill change is required. The repeatable pattern is repo-local: domain packages
should stay framework-free and adapter/parser boundaries should own framework validation and raw
payload mapping.

## Remaining Work

GitHub issue #657 is locally fixed for the cost-engine domain model acceptance criteria pending PR
CI/QA and issue closure. Future cost-engine slices should migrate monetary fields to
`portfolio_common.domain_value_objects` where that reduces calculation ambiguity without changing
downstream contracts.
