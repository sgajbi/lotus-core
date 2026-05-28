# CR-425: Simulation Projection Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service portfolio simulation projected-position assembly.

## Finding

Standalone simulation projection logic used raw `security_id` values as dictionary keys for
baseline positions, simulation changes, and instrument enrichment. Whitespace drift in source
positions, change rows, or returned instruments could split one real security into separate padded
and unpadded projected rows, miss baseline quantities, or leave new simulated positions without
instrument metadata.

That failure mode can make proposal and simulation projections show incorrect quantities, deltas,
position counts, and asset-class metadata even when the underlying portfolio and instrument data is
available.

## Change

Reused the shared query-service security identifier normalizer in `SimulationService`.
Projected-position assembly now trims baseline position identifiers, trims simulation change
identifiers before missing-position detection and quantity application, trims returned instrument
keys, emits canonical projected position identifiers, and fails closed when a simulation change has
no usable security identifier.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_simulation_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/simulation_service.py tests/unit/services/query_service/services/test_simulation_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
simulation-correctness slice that keeps projected positions from fragmenting or losing enrichment
because of whitespace drift in portfolio, simulation, or instrument identifiers.
