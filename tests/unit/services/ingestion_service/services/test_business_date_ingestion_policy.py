from datetime import date

import pytest

from src.services.ingestion_service.app.DTOs.business_date_dto import (
    BusinessDateIngestionRequest,
)
from src.services.ingestion_service.app.services.business_date_ingestion_policy import (
    BUSINESS_DATE_FUTURE_POLICY_VIOLATION_CODE,
    BUSINESS_DATE_MONOTONIC_POLICY_VIOLATION_CODE,
    BUSINESS_DATE_PAYLOAD_EMPTY_CODE,
    BusinessDateIngestionPolicy,
    BusinessDatePolicyViolation,
)

pytestmark = pytest.mark.asyncio


class FakeBusinessCalendarReader:
    def __init__(self, latest_dates: dict[str, date] | None = None):
        self.latest_dates = latest_dates or {}
        self.requested_calendar_codes: list[str] = []

    async def get_latest_business_date(self, calendar_code: str) -> date | None:
        self.requested_calendar_codes.append(calendar_code)
        return self.latest_dates.get(calendar_code)


def _request(*business_dates: dict[str, object]) -> BusinessDateIngestionRequest:
    return BusinessDateIngestionRequest(business_dates=list(business_dates))


async def test_business_date_policy_rejects_empty_payload() -> None:
    policy = BusinessDateIngestionPolicy(FakeBusinessCalendarReader())

    with pytest.raises(BusinessDatePolicyViolation) as exc_info:
        await policy.validate(_request())

    assert exc_info.value.code == BUSINESS_DATE_PAYLOAD_EMPTY_CODE
    assert exc_info.value.message == "At least one business_date record is required."


async def test_business_date_policy_rejects_future_date_beyond_configured_window() -> None:
    policy = BusinessDateIngestionPolicy(
        FakeBusinessCalendarReader(),
        max_future_days=2,
        current_date=lambda: date(2026, 3, 10),
    )

    with pytest.raises(BusinessDatePolicyViolation) as exc_info:
        await policy.validate(_request({"business_date": "2026-03-13"}))

    assert exc_info.value.code == BUSINESS_DATE_FUTURE_POLICY_VIOLATION_CODE
    assert exc_info.value.message == (
        "business_date '2026-03-13' exceeds allowed max '2026-03-12'."
    )


async def test_business_date_policy_rejects_monotonic_regression_when_enabled() -> None:
    reader = FakeBusinessCalendarReader({"GLOBAL": date(2026, 3, 12)})
    policy = BusinessDateIngestionPolicy(
        reader,
        max_future_days=10,
        enforce_monotonic_advance=True,
        current_date=lambda: date(2026, 3, 10),
    )

    with pytest.raises(BusinessDatePolicyViolation) as exc_info:
        await policy.validate(_request({"business_date": "2026-03-11"}))

    assert exc_info.value.code == BUSINESS_DATE_MONOTONIC_POLICY_VIOLATION_CODE
    assert exc_info.value.message == (
        "incoming max business_date '2026-03-11' for calendar_code 'GLOBAL' is older "
        "than latest persisted '2026-03-12'."
    )
    assert reader.requested_calendar_codes == ["GLOBAL"]


async def test_business_date_policy_skips_monotonic_lookup_when_disabled() -> None:
    reader = FakeBusinessCalendarReader({"GLOBAL": date(2026, 3, 12)})
    policy = BusinessDateIngestionPolicy(
        reader,
        max_future_days=10,
        enforce_monotonic_advance=False,
        current_date=lambda: date(2026, 3, 10),
    )

    await policy.validate(_request({"business_date": "2026-03-11"}))

    assert reader.requested_calendar_codes == []
