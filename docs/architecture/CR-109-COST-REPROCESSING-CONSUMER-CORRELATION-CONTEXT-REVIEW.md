# CR-109 Cost Reprocessing Consumer Correlation Context Review

## Scope

- `src/services/calculators/cost_calculator_service/app/consumers/reprocessing_consumer.py`
- `tests/unit/services/calculators/cost_calculator_service/consumer/test_reprocessing_consumer.py`

## Finding

`ReprocessingConsumer.process_message(...)` could be invoked directly without
`BaseConsumer.run()`, but it still relied on ambient `correlation_id_var` state.
That meant transaction replay requests could republish under `"<not-set>"` even
when the Kafka message header already carried the correct correlation id.

This was the same class of defect already fixed for other direct-invocation
consumers in CR-095 through CR-108.

## Action Taken

- Wrapped the reprocessing request path in
  `BaseConsumer._message_correlation_context(...)`
- Added a unit test proving the repository call observes the Kafka header
  correlation id during direct consumer execution

## Result

The cost reprocessing direct path now follows the same durable correlation
contract as the other reviewed consumers. Replay requests no longer depend on
ambient runtime context for audit fidelity.
