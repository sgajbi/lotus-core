from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from portfolio_common.config import (
    BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE,
    BUSINESS_DATE_MAX_FUTURE_DAYS,
)

from ..DTOs.business_date_dto import BusinessDateIngestionRequest

BUSINESS_DATE_PAYLOAD_EMPTY_CODE = "BUSINESS_DATE_PAYLOAD_EMPTY"
BUSINESS_DATE_FUTURE_POLICY_VIOLATION_CODE = "BUSINESS_DATE_FUTURE_POLICY_VIOLATION"
BUSINESS_DATE_MONOTONIC_POLICY_VIOLATION_CODE = "BUSINESS_DATE_MONOTONIC_POLICY_VIOLATION"


class BusinessCalendarReader(Protocol):
    async def get_latest_business_date(self, calendar_code: str) -> date | None: ...


class BusinessDatePolicyViolation(ValueError):
    def __init__(self, *, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_current_date() -> date:
    return datetime.now(UTC).date()


class BusinessDateIngestionPolicy:
    def __init__(
        self,
        business_calendar_reader: BusinessCalendarReader,
        *,
        max_future_days: int = BUSINESS_DATE_MAX_FUTURE_DAYS,
        enforce_monotonic_advance: bool = BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE,
        current_date: Callable[[], date] = utc_current_date,
    ):
        self._business_calendar_reader = business_calendar_reader
        self._max_future_days = max_future_days
        self._enforce_monotonic_advance = enforce_monotonic_advance
        self._current_date = current_date

    async def validate(self, request: BusinessDateIngestionRequest) -> None:
        if not request.business_dates:
            raise BusinessDatePolicyViolation(
                code=BUSINESS_DATE_PAYLOAD_EMPTY_CODE,
                message="At least one business_date record is required.",
            )

        self._assert_business_dates_not_too_far_future(request)
        await self._enforce_business_date_monotonic_advance(request)

    def _assert_business_dates_not_too_far_future(
        self,
        request: BusinessDateIngestionRequest,
    ) -> None:
        max_allowed_date = self._current_date() + timedelta(days=self._max_future_days)
        for row in request.business_dates:
            if row.business_date > max_allowed_date:
                raise BusinessDatePolicyViolation(
                    code=BUSINESS_DATE_FUTURE_POLICY_VIOLATION_CODE,
                    message=(
                        f"business_date '{row.business_date.isoformat()}' exceeds "
                        f"allowed max '{max_allowed_date.isoformat()}'."
                    ),
                )

    async def _enforce_business_date_monotonic_advance(
        self,
        request: BusinessDateIngestionRequest,
    ) -> None:
        if not self._enforce_monotonic_advance:
            return

        calendar_codes = {row.calendar_code for row in request.business_dates}
        for calendar_code in calendar_codes:
            latest_persisted = await self._business_calendar_reader.get_latest_business_date(
                calendar_code
            )
            if latest_persisted is None:
                continue
            incoming_max = max(
                row.business_date
                for row in request.business_dates
                if row.calendar_code == calendar_code
            )
            if incoming_max < latest_persisted:
                raise BusinessDatePolicyViolation(
                    code=BUSINESS_DATE_MONOTONIC_POLICY_VIOLATION_CODE,
                    message=(
                        f"incoming max business_date '{incoming_max.isoformat()}' for "
                        f"calendar_code '{calendar_code}' is older than latest persisted "
                        f"'{latest_persisted.isoformat()}'."
                    ),
                )
