# CR-006 Duplicate Repository Review

## Scope

Pattern review for duplicated repository and near-duplicated runtime ownership across the RFC 81
split services.

Reviewed on:

- `src/services/portfolio_aggregation_service/app/repositories/timeseries_repository.py`
- `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`
- `src/services/valuation_orchestrator_service/app/repositories/valuation_repository.py`
- `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`
- `src/services/portfolio_aggregation_service/app/consumer_manager.py`
- `src/services/timeseries_generator_service/app/consumer_manager.py`

## Findings

### 1. `ValuationRepository` duplication is effectively total

The two valuation repositories are functionally identical.

Current copies:

- `valuation_orchestrator_service`
- `position_valuation_calculator`

This is structural debt because:

- the same eligibility, snapshot, and reprocessing query logic must be kept in sync manually
- a correctness fix can easily land in one copy and not the other
- test coverage can drift and create false confidence

Recommended direction:

- extract a shared valuation repository/query module under a common library or a dedicated shared
  internal package
- keep service-local wrappers only if runtime-specific instrumentation or DTO shaping is needed

### 2. `TimeseriesRepository` duplication is near-total

The two timeseries repositories are almost identical.

Observed difference during review:

- `timeseries_generator_service` adds `get_position_timeseries(...)`
- the rest of the repository is effectively shared logic

This is still structural debt because the most failure-prone query in the branch
(`find_and_claim_eligible_jobs`) exists in both copies.

Recommended direction:

- create a shared timeseries repository base or shared query builder
- keep the worker-only method (`get_position_timeseries`) as a thin extension in the worker service
  if needed

### 3. `ConsumerManager` classes are not the primary duplication problem

The consumer managers for:

- `portfolio_aggregation_service`
- `timeseries_generator_service`

are now intentionally different after RFC 81.

They differ in:

- owned topics
- runtime responsibilities
- web port
- scheduler ownership

Conclusion:

- do not force a direct consumer-manager unification
- instead, review for shared runtime scaffolding patterns later if duplication starts growing again

### 4. Test coverage asymmetry was a real risk

Before the review, the duplicated repository logic was mainly covered from one side.

This created a drift hazard:

- the worker repository could be validated
- the portfolio-aggregation repository could still silently diverge

Action already taken:

- direct unit tests were added for the portfolio-aggregation repository query shape

## Refactor recommendation

Recommended implementation order:

1. Extract shared valuation repository/query logic first
   - highest duplication
   - high correctness sensitivity
2. Extract shared timeseries repository/query logic next
   - especially claim-eligibility and snapshot/position-timeseries query helpers
3. Leave consumer managers split unless a later review shows reusable runtime scaffolding worth
   extracting

## Sign-off state

## Progress update

Implemented in this review program:

- extracted shared valuation query/claim logic into
  `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- reduced both service-local valuation repository files to thin wrappers that preserve:
  - existing import paths
  - service-local metric hooks
  - existing unit/integration test patch points

Validation performed on the converged valuation path:

- unit:
  - `tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py`
  - `tests/unit/services/calculators/position_valuation_calculator/repositories/test_unit_valuation_repo.py`
- integration:
  - `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`
  - `tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py`

Remaining CR-006 scope:

- timeseries repository convergence is still open
- worker-only methods and post-RFC-81 ownership differences need to be handled without
  reintroducing blurred service boundaries

## Sign-off state

Current state: `In Review`

Reason:

- valuation duplication is now converged safely
- timeseries duplication still remains and is the remaining CR-006 refactor target
