"""Server-owned admission for canonical FX cuts; deployed default is deny-all.

This policy consumes the existing verified service principal. It never creates
provider approval from HTTP headers, caller enrollment fields or an auth bypass.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from portfolio_common.domain.market_data.fx_source import (
    FxSourceCut,
    FxSourceScope,
    require_fx_source_identifier,
)
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal

FX_SOURCE_SUBMIT_CAPABILITY = "ingestion.fx_rates.source_cut.submit"


class FxSourceAdmissionRejected(ValueError):
    """Stable source-safe admission refusal; no principal or business payload text."""


@dataclass(frozen=True)
class FxFixingCalendar:
    version: str
    fixing_kind: str
    timezone: str
    fixing_time: time
    publication_delay_seconds: int
    business_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    closed_dates: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        require_fx_source_identifier(self.version)
        require_fx_source_identifier(self.fixing_kind)
        ZoneInfo(self.timezone)
        if (
            not self.version
            or not self.fixing_kind
            or self.fixing_time.tzinfo is not None
            or type(self.publication_delay_seconds) is not int
            or not 0 <= self.publication_delay_seconds <= 86400
            or type(self.business_weekdays) is not tuple
            or not self.business_weekdays
            or any(type(day) is not int or not 0 <= day <= 6 for day in self.business_weekdays)
            or len(set(self.business_weekdays)) != len(self.business_weekdays)
            or type(self.closed_dates) is not tuple
        ):
            raise ValueError("FX_SOURCE_CALENDAR_CONFIGURATION_INVALID")

    def permits(self, business_date: date, observed_at: datetime) -> bool:
        if (
            business_date.weekday() not in self.business_weekdays
            or business_date in self.closed_dates
        ):
            return False
        fixing_at = datetime.combine(business_date, self.fixing_time, ZoneInfo(self.timezone))
        # An enrollment cannot silently choose either side of an ambiguous fixing
        # or normalize a nonexistent wall time through a DST transition.
        if fixing_at.replace(fold=0).utcoffset() != fixing_at.replace(
            fold=1
        ).utcoffset() or fixing_at.astimezone(UTC).astimezone(ZoneInfo(self.timezone)).replace(
            tzinfo=None
        ) != datetime.combine(business_date, self.fixing_time):
            return False
        fixing_utc = fixing_at.astimezone(UTC)
        return (
            fixing_utc
            <= observed_at.astimezone(UTC)
            <= fixing_utc + timedelta(seconds=self.publication_delay_seconds)
        )


@dataclass(frozen=True)
class FxSourceEnrollment:
    version: str
    scope: FxSourceScope
    principal: str
    allowed_pairs: tuple[tuple[str, str], ...]
    calendar_version: str
    valid_from: datetime
    valid_until: datetime
    active: bool = True

    def __post_init__(self) -> None:
        for value in (self.version, self.principal, self.calendar_version):
            require_fx_source_identifier(value)
        if (
            not self.version
            or not self.principal
            or not self.calendar_version
            or type(self.allowed_pairs) is not tuple
            or not self.allowed_pairs
            or len(set(self.allowed_pairs)) != len(self.allowed_pairs)
            or any(
                type(pair) is not tuple
                or len(pair) != 2
                or any(
                    not isinstance(currency, str)
                    or len(currency) != 3
                    or not currency.isascii()
                    or not currency.isalpha()
                    or not currency.isupper()
                    for currency in pair
                )
                or pair[0] == pair[1]
                for pair in self.allowed_pairs
            )
            or self.valid_from.utcoffset() is None
            or self.valid_until.utcoffset() is None
            or self.valid_until <= self.valid_from
            or type(self.active) is not bool
        ):
            raise ValueError("FX_SOURCE_ENROLLMENT_CONFIGURATION_INVALID")


@dataclass(frozen=True)
class FxSourceAdmission:
    cut: FxSourceCut
    accepted_at: datetime
    principal: str
    enrollment_version: str
    calendar_version: str


@dataclass(frozen=True)
class FxSourceAdmissionPolicy:
    enrollments: tuple[FxSourceEnrollment, ...] = ()
    calendars: tuple[FxFixingCalendar, ...] = ()

    def __post_init__(self) -> None:
        if type(self.enrollments) is not tuple or type(self.calendars) is not tuple:
            raise ValueError("FX_SOURCE_POLICY_CONFIGURATION_NOT_IMMUTABLE")
        identities = [(item.scope, item.principal) for item in self.enrollments]
        versions = [item.version for item in self.calendars]
        if len(set(identities)) != len(identities) or len(set(versions)) != len(versions):
            raise ValueError("FX_SOURCE_POLICY_CONFIGURATION_AMBIGUOUS")

    def admit(
        self,
        cut: FxSourceCut,
        *,
        context: TenantContext,
        principal: VerifiedServicePrincipal | None,
        now: datetime,
    ) -> FxSourceAdmission:
        if (
            principal is None
            or not context.identity_verified
            or context.service_identity != principal.service_identity
            or context.tenant_id_text != cut.scope.tenant_id
            or FX_SOURCE_SUBMIT_CAPABILITY not in principal.capabilities
        ):
            raise FxSourceAdmissionRejected("FX_SOURCE_VERIFIED_PRINCIPAL_REQUIRED")
        if now.utcoffset() is None or cut.source_observed_cutoff > now:
            raise FxSourceAdmissionRejected("FX_SOURCE_ACCEPTANCE_TIME_INVALID")
        enrollment = next(
            (
                item
                for item in self.enrollments
                if item.scope == cut.scope and item.principal == principal.service_identity
            ),
            None,
        )
        if (
            enrollment is None
            or not enrollment.active
            or not enrollment.valid_from <= now < enrollment.valid_until
        ):
            raise FxSourceAdmissionRejected("FX_SOURCE_ENROLLMENT_REQUIRED")
        calendar = next(
            (item for item in self.calendars if item.version == enrollment.calendar_version), None
        )
        if calendar is None:
            raise FxSourceAdmissionRejected("FX_SOURCE_CALENDAR_REQUIRED")
        for member in cut.revisions:
            if (member.from_currency, member.to_currency) not in enrollment.allowed_pairs:
                raise FxSourceAdmissionRejected("FX_SOURCE_PAIR_NOT_ENROLLED")
            if (
                member.calendar_version != calendar.version
                or member.fixing_kind != calendar.fixing_kind
                or not calendar.permits(member.rate_date, member.source_observed_at)
            ):
                raise FxSourceAdmissionRejected("FX_SOURCE_FIXING_NOT_ADMITTED")
        return FxSourceAdmission(
            cut=cut,
            accepted_at=now,
            principal=principal.service_identity,
            enrollment_version=enrollment.version,
            calendar_version=calendar.version,
        )
