### **RFC 028: Strengthening Test Strategy with Multi-Layered Coverage**

  * **Status**: **Final**
  * **Date**: 2025-09-02
  * **Services Affected**: All services with consumers (`persistence_service`, all `calculators`, `timeseries_generator_service`), `portfolio-common`, and testing infrastructure.
  * **Related RFCs**: RFC 010 - Test Strategy & Gaps

-----

## 1\. Summary (TL;DR)

Our system's test suite follows a strong pyramid structure, yet a recent incident involving an `AttributeError` from an improperly mocked event object highlighted a critical gap. Our current strategy lacks sufficient coverage at the boundary where services interact with external infrastructure like Kafka, forcing us to rely too heavily on slow, complex end-to-end (E2E) tests as a safety net.

This RFC finalizes the decision to strengthen our testing strategy by introducing two key enhancements to achieve production-grade reliability:

1.  **Mandate Domain-Valid Inputs in Unit Tests**: We will prohibit the mocking of Pydantic event models in unit tests. Tests must use instantiated and validated models to verify schema correctness and business logic simultaneously, catching potential contract drift at the earliest stage.
2.  **Introduce Consumer-Level Integration Tests**: We will create a new, distinct layer of integration tests that validate the boundaries of our Kafka consumers. These tests will use a dedicated test database and an ephemeral Kafka broker to verify the entire consume-process-persist loop for a single service, providing a crucial bridge between unit and E2E tests.

-----

## 2\. Architectural Consequences

### Pros

  * **Higher-Fidelity Unit Tests**: By using real Pydantic models, our unit tests will catch a class of bugs related to schema validation, data types, and required fields that are currently missed, preventing entire categories of runtime errors.
  * **Faster, More Targeted Feedback**: The new consumer-level integration tests will run significantly faster than full E2E tests. This allows developers to isolate and debug issues at a service's boundary (e.g., a Kafka deserialization failure or an atomic database transaction issue) without the noise and delay of a full cross-service pipeline run.
  * **Increased Confidence in Contracts**: This new test layer provides strong guarantees that our services correctly adhere to their event contracts and can handle real-world messages, a significant blind spot in our current strategy.
  * **Improved Developer Experience**: Provides a clear, standardized pattern for testing event-driven components, reducing ambiguity and improving consistency across the codebase.

### Cons / Trade-offs

  * **Increased CI Time**: Consumer-level integration tests, which interact with a database and broker, will be inherently slower than unit tests.
      * **Mitigation**: These tests will be carefully scoped to single consumer workflows and will be configured to run in parallel. Their value in preventing production incidents justifies the modest increase in CI runtime.
  * **Added Complexity**: This introduces a new testing pattern and requires new fixtures (e.g., for managing ephemeral Kafka brokers).
      * **Mitigation**: We will create a single, reusable set of `pytest` fixtures in the root `tests/conftest.py` to abstract away this complexity, making the tests themselves simple to write.

-----

## 3\. High-Level Design

### 3.1. Unit Test Refactoring

  * **Guideline**: Henceforth, any unit test for a function or method that accepts a Pydantic model from our `portfolio-common/events.py` module as an argument **must** instantiate the actual event model. Using `MagicMock` or `mocker.patch` to represent these event objects is prohibited.
  * **Example Refactoring**:
    ```python
    # === BEFORE (PROHIBITED) ===
    def test_some_logic_with_mock():
        mock_event = MagicMock()
        mock_event.transaction_type = "BUY"
        mock_event.epoch = 1
        # ... Test logic ...

    # === AFTER (REQUIRED) ===
    from portfolio_common.events import TransactionEvent

    def test_some_logic_with_validated_model():
        # This event is now guaranteed to be schema-valid
        validated_event = TransactionEvent(
            transaction_id="TXN1",
            portfolio_id="P1",
            # ... other required fields ...
            transaction_type="BUY",
            epoch=1
        )
        # ... Test logic ...
    ```

### 3.2. New Consumer-Level Integration Test Layer

  * **Location**: These tests will reside alongside existing integration tests (e.g., `tests/integration/services/persistence_service/`).
  * **Fixtures**: New, reusable `pytest` fixtures will be implemented in the root `tests/conftest.py` to provide:
      * An ephemeral, test-session-scoped Kafka broker (e.g., via an in-memory implementation or a test container).
      * A test-function-scoped database session that ensures a clean schema for each test run.
  * **Test Workflow**: The tests will follow a standard **Arrange-Act-Assert** pattern:
    1.  **Arrange**: Seed the test database with any prerequisite data (e.g., a `Portfolio` record). Use a test Kafka producer to publish a valid, serialized Pydantic event model to the consumer's input topic.
    2.  **Act**: Instantiate and run the target `BaseConsumer` subclass, allowing it to consume and process the single message from the ephemeral broker.
    3.  **Assert**: Use a database session to query the test database and verify that the expected changes were persisted correctly (e.g., a new `Transaction` row was created). If the consumer produces outbound events, assert that the correct records were written to the `outbox_events` table.

-----

## 4\. Documentation Updates

  * A new, top-level testing strategy document will be created at `docs/testing_strategy.md`. This document will formalize the purpose, scope, and best practices for each layer in our test pyramid:
    1.  **Unit Tests**
    2.  **Component Integration Tests**
    3.  **Consumer-Level Integration Tests**
    4.  **End-to-End (E2E) Tests**
  * Developer guides for services with consumers (e.g., `docs/features/persistence_service/05_Developer_Guide.md`) will be updated to include a section on how to write and run the new consumer-level integration tests.
  * A new `docs/incidents/incident_to_coverage.md` document will be created to map the motivating `AttributeError` incident to the new test cases that now prevent its regression.

-----

## 5\. Acceptance Criteria

1.  A new `docs/testing_strategy.md` document is created, defining the roles and responsibilities of each test layer.
2.  Reusable `pytest` fixtures for an ephemeral Kafka broker and a clean test database are implemented in the root `tests/conftest.py`.
3.  The `test_cashflow_logic.py` unit tests are refactored to use instantiated `TransactionEvent` models instead of mocks.
4.  A new consumer-level integration test suite is implemented for the `PortfolioConsumer` in the `persistence_service`, demonstrating the complete Arrange-Act-Assert workflow.
5.  A new `docs/incidents/incident_to_coverage.md` document is created.
6.  The developer guide for the `persistence_service` (`docs/features/persistence_service/05_Developer_Guide.md`) is updated with instructions for the new test layer.