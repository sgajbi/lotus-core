"""Build deterministic event partition keys from domain-owned identities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_COMPONENT_SEPARATOR = "|"
_MAX_COMPONENT_LENGTH = 160


class PartitionKeyScope(StrEnum):
    """Business scope whose mutations must remain ordered in one event stream."""

    PORTFOLIO = "portfolio"
    PORTFOLIO_SECURITY = "portfolio_security"
    SECURITY = "security"
    CURRENCY_PAIR = "currency_pair"
    BUSINESS_CALENDAR = "business_calendar"
    ORIGINAL_MESSAGE = "original_message"


@dataclass(frozen=True, slots=True)
class EventPartitionKey:
    """Validated transport-neutral partition identity for an ordered event stream."""

    scope: PartitionKeyScope
    components: tuple[str, ...]
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        allow_component_separator = self.scope is PartitionKeyScope.ORIGINAL_MESSAGE
        normalized_components = tuple(
            _normalize_component(
                component,
                field_name="components",
                allow_separator=allow_component_separator,
            )
            for component in self.components
        )
        if not normalized_components:
            raise ValueError("partition key components are required")
        normalized_tenant = (
            _normalize_component(self.tenant_id, field_name="tenant_id")
            if self.tenant_id is not None
            else None
        )
        object.__setattr__(self, "components", normalized_components)
        object.__setattr__(self, "tenant_id", normalized_tenant)

    @property
    def value(self) -> str:
        """Return the stable key value supplied to a partitioned event transport."""

        parts = self.components
        if self.tenant_id is not None:
            parts = (self.tenant_id, *parts)
        return _COMPONENT_SEPARATOR.join(parts)


def portfolio_partition_key(
    portfolio_id: str,
    *,
    tenant_id: str | None = None,
    tenant_required: bool = False,
) -> EventPartitionKey:
    """Order all mutations for one portfolio while allowing other portfolios to proceed."""

    return _build_partition_key(
        scope=PartitionKeyScope.PORTFOLIO,
        components=(portfolio_id,),
        tenant_id=tenant_id,
        tenant_required=tenant_required,
    )


def portfolio_security_partition_key(
    portfolio_id: str,
    security_id: str,
    *,
    tenant_id: str | None = None,
    tenant_required: bool = False,
) -> EventPartitionKey:
    """Order one position timeline across dates, epochs, corrections, and restatements."""

    return _build_partition_key(
        scope=PartitionKeyScope.PORTFOLIO_SECURITY,
        components=(portfolio_id, security_id),
        tenant_id=tenant_id,
        tenant_required=tenant_required,
    )


def security_partition_key(
    security_id: str,
    *,
    tenant_id: str | None = None,
    tenant_required: bool = False,
) -> EventPartitionKey:
    """Order source or derived facts for one security."""

    return _build_partition_key(
        scope=PartitionKeyScope.SECURITY,
        components=(security_id,),
        tenant_id=tenant_id,
        tenant_required=tenant_required,
    )


def currency_pair_partition_key(base_currency: str, quote_currency: str) -> EventPartitionKey:
    """Order all observations and corrections for one directed currency pair."""

    return _build_partition_key(
        scope=PartitionKeyScope.CURRENCY_PAIR,
        components=(base_currency.upper(), quote_currency.upper()),
    )


def business_calendar_partition_key(calendar_code: str) -> EventPartitionKey:
    """Order business-date changes for one governed calendar."""

    return _build_partition_key(
        scope=PartitionKeyScope.BUSINESS_CALENDAR,
        components=(calendar_code.upper(),),
    )


def original_message_partition_key(message_key: str) -> EventPartitionKey:
    """Preserve the original ordering identity for dead-letter and replay transport."""

    return _build_partition_key(
        scope=PartitionKeyScope.ORIGINAL_MESSAGE,
        components=(message_key,),
    )


def _build_partition_key(
    *,
    scope: PartitionKeyScope,
    components: tuple[str, ...],
    tenant_id: str | None = None,
    tenant_required: bool = False,
) -> EventPartitionKey:
    if tenant_required and tenant_id is None:
        raise ValueError(f"tenant_id is required for {scope.value} partition keys")
    return EventPartitionKey(scope=scope, components=components, tenant_id=tenant_id)


def _normalize_component(
    value: str,
    *,
    field_name: str,
    allow_separator: bool = False,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > _MAX_COMPONENT_LENGTH:
        raise ValueError(f"{field_name} must not exceed {_MAX_COMPONENT_LENGTH} characters")
    if not allow_separator and _COMPONENT_SEPARATOR in normalized:
        raise ValueError(f"{field_name} must not contain '{_COMPONENT_SEPARATOR}'")
    if any(character.isspace() and character not in {" "} for character in normalized):
        raise ValueError(f"{field_name} must not contain control whitespace")
    return normalized
