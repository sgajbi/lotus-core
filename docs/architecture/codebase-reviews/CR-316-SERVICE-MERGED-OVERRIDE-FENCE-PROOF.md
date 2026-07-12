# CR-316 Service-Level Merged Override Fence Proof

## Scope
Representative consumer-manager startup path for shared Kafka runtime overrides.

## Finding
`CR-315` proved the merged Kafka override fence at `BaseConsumer` construction, but there was still no representative service-level proof that a real `ConsumerManager` startup path preserved that boundary when constructing multiple consumers with different group ids.

## Fix
Added a valuation-orchestrator consumer-manager proof showing that:
- shared merged `session.timeout.ms` defaults apply to both real consumers
- an invalid merged heartbeat override for the readiness consumer group is dropped
- both consumers retain the safe built-in heartbeat default instead of inheriting an invalid merged value

## Evidence
- `python -m pytest tests/unit/services/valuation_orchestrator_service/unit/test_valuation_orchestrator_consumer_manager_runtime.py -q`
- `python -m ruff check tests/unit/services/valuation_orchestrator_service/unit/test_valuation_orchestrator_consumer_manager_runtime.py`
