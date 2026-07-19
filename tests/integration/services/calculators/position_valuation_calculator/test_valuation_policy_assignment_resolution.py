"""PostgreSQL proof for effective-dated valuation-policy assignment resolution."""

from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import (
    Instrument,
    InstrumentValuationPolicyAssignmentRecord,
)
from portfolio_common.domain.valuation import MissingValuationPolicyAssignmentError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_valuation_calculator.app.infrastructure import (
    SqlAlchemyValuationPolicyAssignmentResolver,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db]


def _assignment(**overrides: object) -> InstrumentValuationPolicyAssignmentRecord:
    values: dict[str, object] = {
        "tenant_id": "LOTUS_PB_SG",
        "legal_book_id": "SG_PRIVATE_BANK_BOOK",
        "security_id": "BOND_US_CORP_2031",
        "policy_id": "CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL",
        "policy_version": 1,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "assignment_status": "ACTIVE",
        "assignment_version": 1,
        "source_system": "security_master",
        "source_record_id": "VALPOL-BOND_US_CORP_2031-PRIMARY",
        "source_revision": "revision-1",
        "observed_at": datetime(2026, 1, 1, tzinfo=UTC),
        "assignment_reason": "Initial clean-price authority",
    }
    values.update(overrides)
    return InstrumentValuationPolicyAssignmentRecord(**values)


async def test_resolver_ranks_corrections_before_lifecycle_and_effective_filters(
    clean_db: None,
    async_db_session: AsyncSession,
) -> None:
    del clean_db
    async_db_session.add(
        Instrument(
            security_id="BOND_US_CORP_2031",
            name="US Corporate Bond 2031",
            isin="US0000002031",
            currency="USD",
            product_type="Bond",
            asset_class="Fixed Income",
        )
    )
    async_db_session.add_all(
        [
            _assignment(),
            _assignment(
                assignment_status="SUSPENDED",
                assignment_version=2,
                source_revision="revision-2",
                observed_at=datetime(2026, 7, 18, tzinfo=UTC),
                assignment_reason="Primary source authority suspended",
            ),
            _assignment(
                policy_id="DIRTY_PERCENT_FACE_MARKET_VALUE",
                source_record_id="VALPOL-BOND_US_CORP_2031-SUCCESSOR",
                source_revision="revision-1",
                valid_from=date(2026, 7, 1),
                assignment_reason="Approved successor dirty-price authority",
            ),
            _assignment(
                tenant_id="LOTUS_PB_HK",
                legal_book_id="HK_PRIVATE_BANK_BOOK",
                source_record_id="VALPOL-BOND_US_CORP_2031-HK",
                assignment_reason="Unrelated tenant authority",
            ),
        ]
    )
    await async_db_session.flush()
    resolver = SqlAlchemyValuationPolicyAssignmentResolver(async_db_session)

    resolved = await resolver.resolve(
        tenant_id="LOTUS_PB_SG",
        legal_book_id="SG_PRIVATE_BANK_BOOK",
        security_id="BOND_US_CORP_2031",
        valuation_date=date(2026, 7, 19),
    )

    assert resolved.policy.policy_id == "DIRTY_PERCENT_FACE_MARKET_VALUE"
    assert resolved.assignment.assignment.source_record_id.endswith("SUCCESSOR")
    assert resolved.assignment.cache_key.tenant_id == "LOTUS_PB_SG"
    assert resolved.assignment.cache_key.legal_book_id == "SG_PRIVATE_BANK_BOOK"

    with pytest.raises(MissingValuationPolicyAssignmentError):
        await resolver.resolve(
            tenant_id="LOTUS_PB_SG",
            legal_book_id="SG_PRIVATE_BANK_BOOK",
            security_id="BOND_US_CORP_2031",
            valuation_date=date(2025, 12, 31),
        )
