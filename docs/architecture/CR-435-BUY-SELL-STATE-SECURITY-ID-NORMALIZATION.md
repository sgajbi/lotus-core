# CR-435: BUY/SELL State Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service BUY lot/accrued-offset lookups and SELL disposal lookups.

## Finding

BUY state and SELL state lookups used raw `security_id` equality for position lots, accrued
income offsets, and SELL disposal transactions. Padded request or persisted identifiers could hide
valid tax-lot lineage, accrued-income offset evidence, or disposal evidence for a holding.

That is a calculation correctness risk because lot state, accrued offsets, and disposal rows
support realized gain/loss, cost-basis, income, and suitability evidence.

## Change

Reused the shared query-service security identifier normalizer in BUY/SELL state services and
repositories. The services now call repositories and return response identity with canonical
security identifiers. Repository lookups now trim request identifiers, fail closed for blanks, and
filter persisted BUY/SELL state rows through trimmed SQL expressions.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_buy_state_repository.py tests/unit/services/query_service/repositories/test_sell_state_repository.py tests/unit/services/query_service/services/test_buy_state_service.py tests/unit/services/query_service/services/test_sell_state_service.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/buy_state_repository.py src/services/query_service/app/repositories/sell_state_repository.py src/services/query_service/app/services/buy_state_service.py src/services/query_service/app/services/sell_state_service.py tests/unit/services/query_service/repositories/test_buy_state_repository.py tests/unit/services/query_service/repositories/test_sell_state_repository.py tests/unit/services/query_service/services/test_buy_state_service.py tests/unit/services/query_service/services/test_sell_state_service.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m pytest tests/unit/services/query_service/services -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
calculation-lineage hardening slice that protects lot, accrual, and disposal evidence from source
identifier padding.
