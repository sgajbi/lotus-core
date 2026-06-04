# CR-881 Cost Consumer Complexity Refactor

Date: 2026-06-02

## Scope

Reduce the cost-calculator consumer orchestration complexity without changing Kafka retry/DLQ
behavior, transaction cost persistence, cash-leg handling, bundle-A diagnostics, or outbox event
contracts.

## Finding

`CostCalculatorConsumer.process_message` in
`src/services/calculators/cost_calculator_service/app/consumer.py` was F-ranked with cyclomatic
complexity `51`. The method mixed the retry/DLQ boundary, idempotency claim, portfolio and
instrument lookup, transaction-domain enrichment, FX contract handling, cost-engine processing,
lot/open-quantity persistence, upstream cash-leg validation, auto-generated cash-leg creation,
bundle-A reconciliation diagnostics, and transaction/instrument outbox emission in one large block.

That made the consumer harder to review as a banking-grade processing path because persistence,
cash-leg policy, diagnostics, and publication responsibilities were not named separately.

## Action

Extracted private consumer helpers for:

1. transaction-domain enrichment and transaction-type normalization,
2. adjustment, FX-contract, and cost-engine event publication preparation,
3. cost-engine input shaping and new-transaction error handling,
4. processed transaction persistence and BUY lot/accrued-offset persistence,
5. upstream-provided cash-leg validation,
6. auto-generated adjustment cash-leg expansion,
7. bundle-A reconciliation diagnostics,
8. processed-transaction and instrument outbox emission.

The public `process_message(msg)` retry/DLQ boundary remains in place.

## Result

`CostCalculatorConsumer.process_message` now reports `C (11)` under Radon instead of `F (51)`, and
the `CostCalculatorConsumer` class aggregate now reports `A (5)`. Repository-wide Xenon no longer
reports an F-ranked block after CR-880 and CR-881.

Broad Xenon complexity enforcement is still not truthful as a repository-wide gate because
`src/libs/portfolio-common/portfolio_common/transaction_domain/fx_linkage.py` remains a D-ranked
module.

## Evidence

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py -q`
  => `26 passed`
- `python -m pytest tests\integration\services\calculators\cost_calculator_service\test_int_cost_consumer_persistence.py -q`
  => `2 passed`
- `python -m radon cc src\services\calculators\cost_calculator_service\app\consumer.py -s`
  => `CostCalculatorConsumer.process_message - C (11)`
- `python -m xenon --max-absolute E --max-modules C --max-average A src` now reports only
  `src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py` as a D-ranked
  module.

## Wiki Decision

No wiki source update is required for this slice. The change is an internal processing
maintainability refactor with repository-local architecture and quality evidence; it does not
change operator-facing runtime behavior, API surface, onboarding flow, or wiki-owned product truth.
