# CR-468: Advisory Simulation Market Data Positive Input Guard

Date: 2026-05-28

## Scope

Canonical advisory simulation request models for market prices and FX rates.

## Finding

The core ingestion and event boundaries now reject non-positive market prices and FX rates, but the
query-control-plane advisory simulation request model still accepted raw decimal market-data
inputs. A zero or negative simulation price/rate could therefore reach portfolio valuation,
funding, allocation, drift, suitability, and proposal-intent logic even when the persisted
authoritative reference-data path would reject the same input.

For private banking proposal execution, simulation market data is calculation input, not free-form
scenario text. Non-positive prices and FX rates can distort projected market value, cash funding,
cross-currency allocation, suitability flags, and proposal evidence.

## Change

Added model-boundary validation so:

1. advisory simulation `Price.price` must be finite and greater than zero,
2. advisory simulation `FxRate.rate` must be finite and greater than zero,
3. the canonical simulation router returns its governed validation problem-details response for
   non-positive market-data payloads.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/advisory_simulation/test_contract_advisory_models.py tests/unit/services/query_service/advisory_simulation/test_valuation.py -q`
2. `python -m pytest tests/unit/services/query_service/advisory_simulation -q`
3. `python -m pytest tests/integration/services/query_service/test_advisory_simulation_router.py -q`
4. `python -m ruff check src/services/query_service/app/advisory_simulation/models.py tests/unit/services/query_service/advisory_simulation/test_contract_advisory_models.py tests/integration/services/query_service/test_advisory_simulation_router.py`
5. `python -m ruff format --check src/services/query_service/app/advisory_simulation/models.py tests/unit/services/query_service/advisory_simulation/test_contract_advisory_models.py tests/integration/services/query_service/test_advisory_simulation_router.py`
6. `git diff --check`

Results:

1. Focused advisory model/valuation proof: `28 passed`
2. Advisory simulation unit pack: `97 passed`
3. Advisory simulation router pack: `6 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Diff hygiene: passed

## Closure

Status: Hardened.

No database migration, wiki source, platform contract, or response-shape change was required. The
canonical advisory simulation contract now rejects non-positive valuation and FX inputs before
calculation logic can produce distorted private-banking proposal evidence.
