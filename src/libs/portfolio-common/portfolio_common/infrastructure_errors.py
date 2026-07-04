from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class InfrastructureError(RuntimeError):
    message: str
    reason_code: str
    dependency: str
    retryable: bool
    safe_context: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)
        object.__setattr__(self, "safe_context", MappingProxyType(dict(self.safe_context)))

    def safe_diagnostics(self) -> dict[str, object]:
        return {
            "reason_code": self.reason_code,
            "dependency": self.dependency,
            "retryable": self.retryable,
            "message": self.message,
            "context": dict(self.safe_context),
        }


class DatabaseUnavailable(InfrastructureError):
    def __init__(
        self,
        *,
        message: str = "Database dependency is unavailable.",
        reason_code: str = "database_unavailable",
        safe_context: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            reason_code=reason_code,
            dependency="database",
            retryable=True,
            safe_context=safe_context or {},
        )


class DatabaseIntegrityViolation(InfrastructureError):
    def __init__(
        self,
        *,
        message: str = "Database integrity constraint failed.",
        reason_code: str = "database_integrity_violation",
        safe_context: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            reason_code=reason_code,
            dependency="database",
            retryable=False,
            safe_context=safe_context or {},
        )


class KafkaPublishBackPressure(InfrastructureError):
    def __init__(
        self,
        *,
        message: str = "Kafka producer local queue is saturated.",
        reason_code: str = "kafka_publish_back_pressure",
        safe_context: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            reason_code=reason_code,
            dependency="kafka",
            retryable=True,
            safe_context=safe_context or {},
        )


class KafkaPublishFailed(InfrastructureError):
    def __init__(
        self,
        *,
        message: str = "Kafka publish failed.",
        reason_code: str = "kafka_publish_failed",
        safe_context: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            reason_code=reason_code,
            dependency="kafka",
            retryable=False,
            safe_context=safe_context or {},
        )


class KafkaPublishUncertain(InfrastructureError):
    def __init__(
        self,
        *,
        message: str = "Kafka publish delivery confirmation is uncertain.",
        reason_code: str = "kafka_publish_uncertain",
        safe_context: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            reason_code=reason_code,
            dependency="kafka",
            retryable=True,
            safe_context=safe_context or {},
        )


class InfrastructureAuditWriteFailed(InfrastructureError):
    def __init__(
        self,
        *,
        message: str = "Audit persistence failed.",
        reason_code: str = "audit_persistence_failed",
        safe_context: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            reason_code=reason_code,
            dependency="database",
            retryable=True,
            safe_context=safe_context or {},
        )
