# CR-880 Advisory Simulation Complexity Refactor

Date: 2026-06-02

## Scope

Reduce the cyclomatic complexity of the query-service advisory proposal simulation engine without
changing the public request/response contract.

## Finding

`run_proposal_simulation` in
`src/services/query_service/app/advisory_simulation/advisory_engine.py` was F-ranked by Xenon. The
function mixed input validation, cash-flow mutation, shelf checks, funding, intent ordering, rule
guard construction, reconciliation, optional drift analytics, suitability scanning, workflow gate
decisioning, and response assembly in one large orchestration block.

That made the endpoint harder to review as a banking workflow because a small policy change could
touch too many concerns at once.

## Action

Extracted named helpers inside the same module for:

1. proposal input validation,
2. cash-flow intent application and negative-cash blocking,
3. shelf-aware security trade intent construction,
4. sell/buy intent splitting and executable buy application,
5. buy dependency linking,
6. after-state construction,
7. proposal guard rule insertion,
8. reconciliation-driven status resolution,
9. optional drift analytics, suitability, and gate-decision calculation.

The public `run_proposal_simulation(...) -> ProposalResult` API remains unchanged.

## Result

`run_proposal_simulation` is now B-ranked by Radon/Xenon-compatible complexity measurement instead
of F-ranked. Existing focused advisory proposal simulation tests continue to pass.

Broad Xenon complexity enforcement is still not truthful as a repository-wide gate. Remaining
complexity debt after this slice:

1. `src/services/calculators/cost_calculator_service/app/consumer.py:227 process_message` remains
   F-ranked,
2. `src/libs/portfolio-common/portfolio_common/transaction_domain/fx_linkage.py` remains a
   D-ranked module.

## Evidence

- `python -m pytest tests\unit\services\query_service\advisory_simulation\test_engine_advisory_proposal_simulation.py -q`
  => `29 passed`
- `python -m radon cc src\services\query_service\app\advisory_simulation\advisory_engine.py -s`
  => `run_proposal_simulation - B (6)`
- `python -m xenon --max-absolute E --max-modules C --max-average A src` now reports only the
  remaining cost-calculator consumer F block and `fx_linkage.py` D module.

## Wiki Decision

No wiki source update is required for this slice. The change records codebase-review evidence and
quality-baseline posture inside repository-local architecture and quality artifacts; it does not
change operator-facing runtime behavior, API surface, onboarding flow, or wiki-owned product truth.
