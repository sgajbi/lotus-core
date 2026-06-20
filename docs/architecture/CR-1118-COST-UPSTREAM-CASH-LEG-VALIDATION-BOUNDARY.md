# CR-1118: Cost Upstream Cash-Leg Validation Boundary

Date: 2026-06-20

## Scope

`CostCalculatorConsumer._validate_upstream_cash_leg(...)` still mixed shared cash-entry-mode policy,
adjustment-leg bypass behavior, product-leg external cash ID validation, repository lookup,
retryable missing-cash-leg behavior, DTO mapping, and dual-leg pairing assertion in one B-ranked
consumer method. The cash-entry-mode and pairing rules already live in
`portfolio_common.transaction_domain`; the consumer should only orchestrate repository access and
call those shared policy helpers.

## Change

- Replaced inline upstream-mode comparison with the shared
  `is_upstream_provided_cash_entry_mode(...)` policy helper.
- Extracted upstream-validation predicate, required external cash ID resolution, and persisted cash
  leg loading into focused helpers.
- Preserved `assert_portfolio_flow_cash_entry_mode_allowed(...)`,
  `assert_upstream_cash_leg_pairing(...)`, and retryable missing-cash-leg behavior.
- Added a direct regression test proving upstream-provided product legs without an external cash
  transaction ID fail before repository lookup.

## Evidence

Local proof:

- `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py -q`
- `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer tests/unit/services/calculators/cost_calculator_service/engine -q`
- `python -m ruff check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
- `python -m ruff format --check src/services/calculators/cost_calculator_service/app/consumer.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
- `make lint`
- `make typecheck`
- `make quality-maintainability-gate`
- `make quality-complexity-gate`
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- `git diff --check`
- Radon no longer reports `_validate_upstream_cash_leg` in the B-ranked hotspot list; the remaining
  consumer hotspot is `_build_cost_engine_events_to_publish` at `B (6)`, and `consumer.py` remains
  A-ranked maintainability at `A (20.32)`.

## Follow-Up

Continue with `_build_cost_engine_events_to_publish` only as a separate slice because it covers
history loading, engine transformation, FX enrichment, processor orchestration, persistence, and lot
state updates.
