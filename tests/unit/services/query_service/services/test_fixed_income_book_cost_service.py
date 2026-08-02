"""Verify public as-of book-cost evidence is date-correct and fail closed."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import (
    LotAmortizedCostPeriodRecord,
    LotAmortizedCostProfileRecord,
)
from sqlalchemy.ext.asyncio import AsyncSession

from services.query_service.app.repositories.fixed_income_book_cost_repository import (
    FixedIncomeBookCostAsOfReadRecord,
    FixedIncomeBookCostReadRepository,
    _period_read_record,
    _profile_read_record,
)
from services.query_service.app.services.fixed_income_book_cost_service import (
    FixedIncomeBookCostService,
)


def _profile(*, status: str = "ACTIVE") -> LotAmortizedCostProfileRecord:
    active = status == "ACTIVE"
    return LotAmortizedCostProfileRecord(
        profile_id="profile-001",
        profile_version=2,
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="PORTFOLIO_001",
        security_id="BOND_001",
        lot_id="LOT_001",
        effective_date=date(2026, 1, 1),
        status=status,
        eligibility_reason=None if active else "POLICY_UNSUPPORTED",
        policy_id="IFRS9_EIR_LOCAL" if active else None,
        policy_version=1 if active else None,
        schedule_version=1 if active else None,
        currency="USD" if active else None,
        direction="DISCOUNT_ACCRETION" if active else None,
        initial_amortized_cost_local=Decimal("980") if active else None,
        redemption_value_local=Decimal("1000") if active else None,
        final_amortized_cost_local=Decimal("1000") if active else None,
        residual_local=Decimal("0") if active else None,
        authority_content_hash="a" * 64,
        source_references=[
            {
                "source_system": "accounting-policy-master",
                "source_record_id": "basis-001",
                "source_revision": "revision-1",
                "source_content_hash": "b" * 64,
                "observed_at": "2026-01-01T00:00:00+00:00",
            }
        ],
        calculation_lineage=(
            {
                "algorithm_id": "fixed-income-amortized-cost-schedule",
                "algorithm_version": 1,
                "intermediate_precision": 38,
                "input_content_hash": "c" * 64,
                "calculation_content_hash": "d" * 64,
                "output_content_hash": "e" * 64,
                "numeric_output_policy": None,
            }
            if active
            else None
        ),
        profile_content_hash="f" * 64,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _period(
    *,
    ordinal: int,
    start: date,
    end: date,
    begin: str,
    finish: str,
) -> LotAmortizedCostPeriodRecord:
    return LotAmortizedCostPeriodRecord(
        profile_id="profile-001",
        profile_version=2,
        period_ordinal=ordinal,
        period_start_date=start,
        period_end_date=end,
        year_fraction=Decimal("0.5"),
        period_rate=Decimal("0.025"),
        begin_amortized_cost_local=Decimal(begin),
        interest_income_local=Decimal("24.5"),
        cash_coupon_local=Decimal("20"),
        amortization_amount_local=Decimal("4.5"),
        end_amortized_cost_local=Decimal(finish),
        rounding_adjustment_local=Decimal("0"),
        calculation_output_hash="1" * 64,
        period_content_hash=str(ordinal) * 64,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _service(result) -> FixedIncomeBookCostService:
    if result is not None:
        profile, periods = result
        result = FixedIncomeBookCostAsOfReadRecord(
            profile=_profile_read_record(profile),
            periods=tuple(_period_read_record(period) for period in periods),
        )
    service = FixedIncomeBookCostService(MagicMock(spec=AsyncSession))
    service._repository = MagicMock()
    service._repository.effective_as_of = AsyncMock(return_value=result)
    return service


@pytest.mark.asyncio
async def test_as_of_uses_latest_completed_period_without_interpolation() -> None:
    periods = [
        _period(
            ordinal=1,
            start=date(2026, 1, 1),
            end=date(2026, 6, 30),
            begin="980",
            finish="984.5",
        ),
        _period(
            ordinal=2,
            start=date(2026, 6, 30),
            end=date(2026, 12, 31),
            begin="984.5",
            finish="1000",
        ),
    ]
    service = _service((_profile(), periods))

    response = await service.get_as_of(
        tenant_id=" TENANT_SG ",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="PORTFOLIO_001",
        security_id="BOND_001",
        lot_id="LOT_001",
        as_of_date=date(2026, 9, 30),
    )

    assert response.book_cost_local_as_of == Decimal("984.5")
    assert response.recognized_through_date == date(2026, 6, 30)
    assert response.next_recognition_date == date(2026, 12, 31)
    assert response.recognized_period_count == 1
    assert response.total_period_count == 2
    assert response.latest_recognized_period is not None
    assert response.latest_recognized_period.period_ordinal == 1
    assert response.calculation_lineage is not None
    assert response.calculation_lineage.input_content_hash == "c" * 64
    assert response.source_references[0].source_record_id == "basis-001"
    call = service._repository.effective_as_of.await_args.kwargs
    assert call["tenant_id"] == "TENANT_SG"


@pytest.mark.asyncio
async def test_before_first_period_returns_opening_book_cost_and_next_date() -> None:
    periods = [
        _period(
            ordinal=1,
            start=date(2026, 1, 1),
            end=date(2026, 6, 30),
            begin="980",
            finish="984.5",
        )
    ]

    response = await _service((_profile(), periods)).get_as_of(
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="PORTFOLIO_001",
        security_id="BOND_001",
        lot_id="LOT_001",
        as_of_date=date(2026, 3, 31),
    )

    assert response.book_cost_local_as_of == Decimal("980")
    assert response.recognized_through_date is None
    assert response.next_recognition_date == date(2026, 6, 30)
    assert response.latest_recognized_period is None


@pytest.mark.asyncio
async def test_parked_profile_returns_reason_without_calculated_amount() -> None:
    response = await _service((_profile(status="PARKED"), [])).get_as_of(
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="PORTFOLIO_001",
        security_id="BOND_001",
        lot_id="LOT_001",
        as_of_date=date(2026, 3, 31),
    )

    assert response.status == "PARKED"
    assert response.eligibility_reason == "POLICY_UNSUPPORTED"
    assert response.book_cost_local_as_of is None
    assert response.calculation_lineage is None


@pytest.mark.asyncio
async def test_missing_exact_scope_profile_is_not_substituted() -> None:
    with pytest.raises(LookupError, match="exact tenant/legal-book"):
        await _service(None).get_as_of(
            tenant_id="TENANT_SG",
            legal_book_id="BOOK_SG_PB",
            portfolio_id="PORTFOLIO_001",
            security_id="BOND_001",
            lot_id="LOT_404",
            as_of_date=date(2026, 3, 31),
        )


@pytest.mark.asyncio
async def test_repository_returns_none_when_exact_scope_has_no_effective_profile() -> None:
    profile_result = MagicMock()
    profile_result.first.return_value = None
    db = MagicMock(spec=AsyncSession)
    db.scalars = AsyncMock(return_value=profile_result)

    result = await FixedIncomeBookCostReadRepository(db).effective_as_of(
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="PORTFOLIO_001",
        security_id="BOND_001",
        lot_id="LOT_404",
        as_of_date=date(2026, 3, 31),
    )

    assert result is None
    db.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_repository_maps_profile_and_ordered_periods_to_read_records() -> None:
    profile = _profile()
    period = _period(
        ordinal=1,
        start=date(2026, 1, 1),
        end=date(2026, 6, 30),
        begin="980",
        finish="984.5",
    )
    profile_result = MagicMock()
    profile_result.first.return_value = profile
    period_result = MagicMock()
    period_result.all.return_value = [period]
    db = MagicMock(spec=AsyncSession)
    db.scalars = AsyncMock(side_effect=[profile_result, period_result])

    result = await FixedIncomeBookCostReadRepository(db).effective_as_of(
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        portfolio_id="PORTFOLIO_001",
        security_id="BOND_001",
        lot_id="LOT_001",
        as_of_date=date(2026, 9, 30),
    )

    assert result is not None
    assert result.profile.profile_id == "profile-001"
    assert result.profile.source_references[0]["source_record_id"] == "basis-001"
    assert result.periods[0].period_ordinal == 1
    assert result.periods[0].end_amortized_cost_local == Decimal("984.5")
    assert db.scalars.await_count == 2


@pytest.mark.asyncio
async def test_non_string_scope_identifier_fails_before_repository_access() -> None:
    service = _service(None)

    with pytest.raises(TypeError, match="tenant_id must be a string"):
        await service.get_as_of(
            tenant_id=1,  # type: ignore[arg-type]
            legal_book_id="BOOK_SG_PB",
            portfolio_id="PORTFOLIO_001",
            security_id="BOND_001",
            lot_id="LOT_001",
            as_of_date=date(2026, 3, 31),
        )

    service._repository.effective_as_of.assert_not_awaited()


@pytest.mark.asyncio
async def test_blank_scope_identifier_fails_before_repository_access() -> None:
    service = _service(None)

    with pytest.raises(ValueError, match="legal_book_id must be nonblank"):
        await service.get_as_of(
            tenant_id="TENANT_SG",
            legal_book_id="  ",
            portfolio_id="PORTFOLIO_001",
            security_id="BOND_001",
            lot_id="LOT_001",
            as_of_date=date(2026, 3, 31),
        )

    service._repository.effective_as_of.assert_not_awaited()
