# CR-018 Cost Basis Vocabulary Review

## Scope

Canonical ownership of `cost_basis_method` vocabulary after the financial engine
config/runtime cleanup.

## Findings

`src/libs/financial-calculator-engine/src/core/enums/cost_method.py` was no
longer a live owner of cost-basis vocabulary.

- it had no production imports after `core/config/settings.py` was removed
- the real live surface was broader than the engine:
  - `PortfolioEvent`
  - ingestion portfolio DTOs
  - persistence of `portfolios.cost_basis_method`
  - sell linkage policy assignment
  - cost-calculator strategy selection

The repo was also carrying an uncontrolled alias split:

- canonical live value: `AVCO`
- stale alias: `AVERAGE_COST`

Because the project is not live yet, carrying that alias forward would be
unnecessary debt. The correct move is to reject it, not normalize it.

## Actions taken

- Introduced shared canonical vocabulary in
  `src/libs/portfolio-common/portfolio_common/cost_basis.py`
- Added `normalize_cost_basis_method(...)`
- Typed `PortfolioEvent.cost_basis_method` and ingestion portfolio DTOs with the
  shared enum
- Normalized persistence writes in `PortfolioRepository`
- Normalized sell linkage policy resolution
- Normalized cost-calculator strategy selection
- Added regression tests for:
  - canonical values
  - rejection of stale alias values
- Removed the dead engine-local enum file

## Rationale

`cost_basis_method` is portfolio metadata and cross-service business vocabulary.
It should not be owned by a single calculator library.

The correct ownership boundary is `portfolio-common`, where the canonical event
and metadata contract already lives.

## Follow-up

Do not add `AVERAGE_COST` or other compatibility aliases back into the codebase
unless the project later has a real external backward-compatibility obligation.

## Evidence

- `src/libs/portfolio-common/portfolio_common/cost_basis.py`
- `src/libs/portfolio-common/portfolio_common/events.py`
- `src/services/ingestion_service/app/DTOs/portfolio_dto.py`
- `src/services/persistence_service/app/repositories/portfolio_repository.py`
- `src/libs/portfolio-common/portfolio_common/transaction_domain/sell_linkage.py`
- `src/services/calculators/cost_calculator_service/app/consumer.py`
- `tests/unit/libs/portfolio_common/test_cost_basis.py`
- `tests/integration/services/persistence_service/repositories/test_repositories.py`
