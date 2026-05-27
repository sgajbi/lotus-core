# CR-377: Transaction Quantity Effect Type Normalization

Date: 2026-05-28

## Scope

Query-service shared transaction quantity-effect calculation used by simulation and core snapshot
projected-position assembly.

## Finding

`transaction_quantity_effect_decimal` uppercased transaction type values without trimming source
whitespace. Padded lower-case values such as ` sell ` or ` deposit ` could miss the governed
transaction-type sets and return a zero quantity effect instead of the correct increase or decrease.

This mattered because the helper is shared by simulation and core snapshot projected-position
calculations. A missed transaction type could leave simulated positions unchanged or understate cash
book movement.

## Change

Trimmed transaction type values before uppercase normalization in the shared quantity-effect helper.
Extended direct helper tests to prove padded `buy`, `sell`, and `deposit` values preserve the
expected position or cash movement sign.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_position_flow_effects.py tests/unit/services/query_service/services/test_core_snapshot_service.py tests/unit/services/query_service/services/test_simulation_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/position_flow_effects.py tests/unit/services/query_service/services/test_position_flow_effects.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
calculation-path reliability hardening slice for simulation and core snapshot projections.
