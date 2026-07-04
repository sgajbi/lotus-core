from portfolio_common.infrastructure_errors import (
    InfrastructureAuditWriteFailed,
    KafkaPublishBackPressure,
)


def test_infrastructure_error_exposes_source_safe_diagnostics() -> None:
    error = KafkaPublishBackPressure(safe_context={"topic": "transactions.raw.received"})

    assert str(error) == "Kafka producer local queue is saturated."
    assert error.safe_diagnostics() == {
        "reason_code": "kafka_publish_back_pressure",
        "dependency": "kafka",
        "retryable": True,
        "message": "Kafka producer local queue is saturated.",
        "context": {"topic": "transactions.raw.received"},
    }


def test_audit_write_failure_is_retryable_database_infrastructure_error() -> None:
    error = InfrastructureAuditWriteFailed(
        message="Unable to record consumer DLQ replay audit.",
        reason_code="audit_persistence_failed",
    )

    assert error.dependency == "database"
    assert error.retryable is True
    assert error.safe_diagnostics()["reason_code"] == "audit_persistence_failed"
