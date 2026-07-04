# Testability Architecture Standard

Core business logic must be testable without FastAPI, real databases, Kafka, Redis, cloud SDKs, or
real downstream APIs.

## Protected Modules

The machine-readable contract lives at
`docs/standards/testability-architecture-contract.json`.

The current protected set covers:

1. `src/services/**/app/domain/**/*.py`,
2. `src/services/**/app/application/**/*.py`,
3. `src/services/**/app/ports/**/*.py`,
4. `src/services/**/app/policies/**/*.py`,
5. `src/services/calculators/position_calculator/app/core/position_reducer.py`.

Add modules to this contract when a slice extracts business policy, application use cases, ports,
or pure reducers from legacy service files.

## Forbidden Runtime Dependencies

Protected modules must not import or directly call:

1. FastAPI or Starlette request/response/dependency objects,
2. SQLAlchemy sessions or `portfolio_common.db` runtime factories,
3. concrete Kafka utilities or producer factories,
4. Redis, HTTP client, cloud SDK, or downstream API clients,
5. repository, router, dependency, consumer, infrastructure, adapter, or client packages.

## Approved Composition Roots

Runtime wiring belongs in composition or infrastructure locations such as:

1. `app/dependencies.py`,
2. `app/main.py` and `app/web.py`,
3. `app/routers/`,
4. `app/consumers/` and `app/consumer_manager.py`,
5. `app/adapters/`,
6. `app/infrastructure/`,
7. `app/repositories/`,
8. shared infrastructure modules such as `portfolio_common.db`, `portfolio_common.kafka_utils`,
   `portfolio_common.event_publisher`, `portfolio_common.outbox_dispatcher`,
   `portfolio_common.http_app_bootstrap`, and `portfolio_common.health`.

These locations may construct concrete sessions, repositories, clients, producers, middleware, and
framework adapters. Protected modules receive only ports, protocols, values, commands, or policy
inputs.

## Use Case Pattern

Use cases depend on explicit ports and are tested with fakes:

```python
from dataclasses import dataclass
from typing import Protocol


class PortfolioReader(Protocol):
    async def load(self, portfolio_id: str) -> object | None: ...


@dataclass(frozen=True, slots=True)
class LoadPortfolioCommand:
    portfolio_id: str


class LoadPortfolioUseCase:
    def __init__(self, reader: PortfolioReader) -> None:
        self._reader = reader

    async def execute(self, command: LoadPortfolioCommand) -> object | None:
        return await self._reader.load(command.portfolio_id)
```

Tests provide an in-memory fake `PortfolioReader`; dependency modules wire SQLAlchemy-backed
readers for runtime.

## Enforcement

`make architecture-guard` runs `scripts/testability_architecture_guard.py`.

When the guard fails, it reports the protected module path, line, rule, and offending import or
runtime call. Fix by moving runtime construction to an approved composition root, adding or reusing
a port, and testing the protected module with a fake adapter.

## Compatibility

This is an architecture and testability rule. It does not change route paths, API DTOs, event
payloads, database schemas, metric names, or runtime topology by itself.
