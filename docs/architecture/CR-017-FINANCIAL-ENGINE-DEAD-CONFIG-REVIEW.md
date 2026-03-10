# CR-017 Financial Engine Dead Config Review

## Scope

Dead configuration/runtime surface inside `financial-calculator-engine`.

## Findings

The shared library still contained an orphaned config layer:

- `src/libs/financial-calculator-engine/src/core/config/settings.py`

That module defined:

- app metadata
- API prefix
- log level
- cost-basis method
- decimal precision

But it had no live imports from production code, tests, or scripts.

This was stale scaffolding from an older “standalone API” shape for the engine,
not part of the current `lotus-core` architecture.

It also kept two package dependencies alive for no live reason:

- `pydantic-settings`
- `python-dotenv`

## Actions taken

- Removed the dead `core/config/settings.py` module.
- Removed the now-unused library dependencies from
  `src/libs/financial-calculator-engine/pyproject.toml`.

## Rationale

Keeping dead config scaffolding in a shared library is harmful:

- it suggests a runtime contract that does not exist
- it increases maintenance surface
- it keeps stale dependencies in the package graph

The shared library should contain reusable domain logic only, not a phantom app
runtime layer.

## Follow-up

The remaining `core/enums/cost_method.py` is currently low-usage and should be
reviewed separately before removal or broader adoption. It represents domain
vocabulary rather than a dead runtime contract.

## Evidence

- deleted `src/libs/financial-calculator-engine/src/core/config/settings.py`
- updated `src/libs/financial-calculator-engine/pyproject.toml`
