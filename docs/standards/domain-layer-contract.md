# Domain Layer Contract

The domain layer is the private-banking business language of `lotus-core`.

Domain modules own business models, value objects, calculation policies, lifecycle policies,
business-rule validation, state-transition policy, and domain vocabulary. They must not depend on
API, event, persistence, infrastructure, or runtime framework concerns.

## Package Convention

Use one of these package shapes:

1. Service-owned domain logic: `src/services/<service>/app/domain/`.
2. Nested bounded contexts inside a service: `src/services/<service>/app/<context>/domain/`.
3. Shared bounded-context logic: `src/libs/portfolio-common/portfolio_common/domain/<context>/`.
4. Shared value objects: self-explanatory modules under the owning shared domain context, such as
   `src/libs/portfolio-common/portfolio_common/domain/financial/amounts.py`.

Do not add flat `*_domain.py`, `domain_value_objects.py`, `utils.py`, or `helpers.py` buckets. A
shared domain placement requires multiple genuine consumers; service-owned calculation policy stays
inside that service's domain package.

## Allowed Dependencies

Domain modules may import:

1. Python standard library modules,
2. pure shared value objects and policies,
3. sibling domain modules,
4. domain enums and constants.

## Disallowed Dependencies

Domain modules must not import:

1. FastAPI, Starlette, Pydantic, SQLAlchemy, Kafka clients, Redis clients, HTTP clients, or concrete
   settings;
2. API DTO packages, event DTO packages, routers, repositories, clients, consumers, database
   sessions, outbox publishers, or transport adapters;
3. persistence models or downstream response models as domain objects.

Transitional exceptions must be explicit in `scripts/quality/domain_layer_guard.py` with a narrow rationale
and should be removed as the owning domain model is migrated.

## Current Guard

Run:

```powershell
make domain-layer-guard
```

`make architecture-guard` also runs the domain-layer guard.

## Representative Implementations

Current pure-domain examples include:

1. ingestion job lifecycle policy;
2. financial reconciliation run lifecycle policy;
3. financial reconciliation position-valuation policy and domain finding objects;
4. cost-basis transaction, fee, and calculation-error domain models;
5. shared currency, money, FX-rate, quantity, and unit-price values in
   `portfolio_common.domain.financial.amounts`;
6. shared positive FX-rate, positive market-price, and valuation-unit-price policies in
   `portfolio_common.domain.market_data`.
