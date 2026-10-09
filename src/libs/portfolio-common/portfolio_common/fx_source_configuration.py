"""Explicit deployment enrollment/calendar/key inputs; no real provider defaults."""

from dataclasses import dataclass
from datetime import date, time

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter

from .domain.market_data.fx_source import FxSourceScope
from .fx_cut_authorization import FxCutRelayKey, FxCutRelayPolicy
from .fx_source_admission import FxFixingCalendar, FxSourceAdmissionPolicy, FxSourceEnrollment
from .runtime_settings import env_str


class FxSourceConfigurationRejected(ValueError):
    """No configuration payload, secret variable or identity is exposed in errors."""


class _ConfigurationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _EnrollmentEntry(_ConfigurationEntry):
    version: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    provider_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    principal: str = Field(min_length=1, max_length=128)
    allowed_pairs: tuple[tuple[str, str], ...] = Field(min_length=1, max_length=128)
    calendar_version: str = Field(min_length=1, max_length=128)
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    active: bool = Field(default=False, strict=True)


class _CalendarEntry(_ConfigurationEntry):
    version: str = Field(min_length=1, max_length=128)
    fixing_kind: str = Field(min_length=1, max_length=128)
    timezone: str = Field(min_length=1, max_length=128)
    fixing_time: time
    publication_delay_seconds: int = Field(ge=0, le=86400, strict=True)
    business_weekdays: tuple[int, ...] = Field(min_length=1, max_length=7)
    closed_dates: tuple[date, ...] = Field(default=(), max_length=4096)


class _RelayEntry(_ConfigurationEntry):
    issuer: str = Field(min_length=1, max_length=128)
    key_id: str = Field(min_length=1, max_length=128)
    secret_env: str = Field(pattern="^LOTUS_FX_SOURCE_RELAY_KEY_[A-Z0-9_]{1,64}$")
    signing_enabled: bool = Field(default=False, strict=True)


@dataclass(frozen=True)
class FxSourcePolicies:
    admission: FxSourceAdmissionPolicy
    relay: FxCutRelayPolicy


def _registry(name: str) -> str:
    raw: str = env_str(name, "[]")
    if len(raw.encode("utf-8")) > 65536:
        raise FxSourceConfigurationRejected("FX_SOURCE_CONFIGURATION_INVALID")
    return raw


def load_fx_source_policies() -> FxSourcePolicies:
    try:
        enrollments = TypeAdapter(list[_EnrollmentEntry]).validate_json(
            _registry("LOTUS_FX_SOURCE_ENROLLMENTS")
        )
        calendars = TypeAdapter(list[_CalendarEntry]).validate_json(
            _registry("LOTUS_FX_SOURCE_CALENDARS")
        )
        keys = TypeAdapter(list[_RelayEntry]).validate_json(_registry("LOTUS_FX_SOURCE_RELAY_KEYS"))
        if len(enrollments) > 64 or len(calendars) > 64 or len(keys) > 4:
            raise ValueError("bounded registry")
        admission = FxSourceAdmissionPolicy(
            tuple(
                FxSourceEnrollment(
                    scope=FxSourceScope(item.tenant_id, item.provider_id, item.source_id),
                    **item.model_dump(exclude={"tenant_id", "provider_id", "source_id"}),
                )
                for item in enrollments
            ),
            tuple(FxFixingCalendar(**item.model_dump()) for item in calendars),
        )
        relay = FxCutRelayPolicy(
            tuple(
                FxCutRelayKey(
                    issuer=item.issuer,
                    key_id=item.key_id,
                    secret=env_str(item.secret_env, ""),
                    signing_enabled=item.signing_enabled,
                )
                for item in keys
            )
        )
        return FxSourcePolicies(admission, relay)
    except (ValueError, TypeError, KeyError):
        raise FxSourceConfigurationRejected("FX_SOURCE_CONFIGURATION_INVALID") from None
