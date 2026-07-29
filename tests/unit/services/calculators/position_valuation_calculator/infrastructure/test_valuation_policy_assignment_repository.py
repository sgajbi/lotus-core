"""Tests for the service-local valuation-policy assignment infrastructure adapter."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import InstrumentValuationPolicyAssignmentRecord
from portfolio_common.domain.valuation import (
    MissingValuationPolicyAssignmentError,
    OverlappingValuationPolicyAssignmentError,
    UnknownValuationPolicyError,
    ValuationAuthorityScope,
)
from sqlalchemy.dialects import postgresql

from src.services.calculators.position_valuation_calculator.app.infrastructure import (
    SqlAlchemyValuationPolicyAssignmentResolver,
)
from src.services.calculators.position_valuation_calculator.app.ports import (
    ValuationPolicyAuthorityRequest,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


def _record(**overrides: object) -> InstrumentValuationPolicyAssignmentRecord:
    values: dict[str, object] = {
        "tenant_id": "LOTUS_PB_SG",
        "legal_book_id": "SG_PRIVATE_BANK_BOOK",
        "security_id": "BOND_US_CORP_2031",
        "policy_id": "CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL",
        "policy_version": 1,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "assignment_status": "ACTIVE",
        "assignment_version": 2,
        "source_system": "security_master",
        "source_record_id": "VALPOL-BOND_US_CORP_2031-SG",
        "source_revision": "revision-2",
        "observed_at": datetime(2026, 7, 19, 9, 30, tzinfo=UTC),
        "assignment_reason": "Approved clean-price fixed-income treatment",
    }
    values.update(overrides)
    return InstrumentValuationPolicyAssignmentRecord(**values)


def _session_returning(*records: InstrumentValuationPolicyAssignmentRecord) -> AsyncMock:
    session = AsyncMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: list(records))
    return session


def _request(
    *,
    tenant_id: str = "LOTUS_PB_SG",
    legal_book_id: str = "SG_PRIVATE_BANK_BOOK",
    security_id: str = "BOND_US_CORP_2031",
    valuation_date: date = date(2026, 7, 19),
) -> ValuationPolicyAuthorityRequest:
    return ValuationPolicyAuthorityRequest(
        scope=ValuationAuthorityScope(
            tenant_id=tenant_id,
            legal_book_id=legal_book_id,
            security_id=security_id,
        ),
        valuation_date=valuation_date,
    )


async def test_resolve_binds_exact_assignment_to_exact_registered_policy_in_one_query() -> None:
    session = _session_returning(_record())
    resolver = SqlAlchemyValuationPolicyAssignmentResolver(session)
    request = _request(
        tenant_id=" LOTUS_PB_SG ",
        legal_book_id=" SG_PRIVATE_BANK_BOOK ",
        security_id=" BOND_US_CORP_2031 ",
    )

    resolved_by_key = await resolver.resolve_many([request])
    resolved = resolved_by_key[request.key]

    assert resolved.policy.policy_id == "CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL"
    assert resolved.policy.policy_version == 1
    assert resolved.assignment.assignment.assignment_version == 2
    assert resolved.assignment.cache_key.source_revision == "revision-2"
    assert len(resolved.assignment.cache_key.assignment_content_hash) == 64
    session.scalars.assert_awaited_once()

    statement = session.scalars.await_args.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "row_number() OVER" in compiled
    assert "PARTITION BY" in compiled
    assert "assignment_version DESC" in compiled
    assert "source_rank" in compiled


async def test_resolve_fails_closed_when_no_effective_authority_exists() -> None:
    resolver = SqlAlchemyValuationPolicyAssignmentResolver(_session_returning())

    with pytest.raises(MissingValuationPolicyAssignmentError, match="exact tenant"):
        await resolver.resolve_many([_request()])


async def test_resolve_fails_closed_when_durable_authorities_overlap() -> None:
    resolver = SqlAlchemyValuationPolicyAssignmentResolver(
        _session_returning(
            _record(),
            _record(
                source_record_id="VALPOL-BOND_US_CORP_2031-SECONDARY",
                source_revision="revision-1",
                assignment_version=1,
            ),
        )
    )

    with pytest.raises(OverlappingValuationPolicyAssignmentError, match="overlapping active"):
        await resolver.resolve_many([_request()])


async def test_resolve_fails_closed_when_assignment_references_unknown_policy_version() -> None:
    resolver = SqlAlchemyValuationPolicyAssignmentResolver(
        _session_returning(_record(policy_version=99))
    )

    with pytest.raises(UnknownValuationPolicyError, match="unsupported valuation policy"):
        await resolver.resolve_many([_request()])


@pytest.mark.parametrize("field_name", ["tenant_id", "legal_book_id", "security_id"])
async def test_resolve_rejects_blank_scope_before_database_access(field_name: str) -> None:
    session = _session_returning()
    resolver = SqlAlchemyValuationPolicyAssignmentResolver(session)
    scope = {
        "tenant_id": "LOTUS_PB_SG",
        "legal_book_id": "SG_PRIVATE_BANK_BOOK",
        "security_id": "BOND_US_CORP_2031",
    }
    scope[field_name] = "   "

    with pytest.raises(ValueError, match=field_name):
        await resolver.resolve_many([_request(**scope)])

    session.scalars.assert_not_awaited()


async def test_resolve_many_deduplicates_requests_and_resolves_dates_from_one_query() -> None:
    session = _session_returning(_record())
    resolver = SqlAlchemyValuationPolicyAssignmentResolver(session)
    first = _request(valuation_date=date(2026, 7, 19))
    second = _request(valuation_date=date(2026, 7, 20))

    resolved = await resolver.resolve_many([first, first, second])

    assert set(resolved) == {first.key, second.key}
    assert resolved[first.key].assignment.cache_key.valuation_date == date(2026, 7, 19)
    assert resolved[second.key].assignment.cache_key.valuation_date == date(2026, 7, 20)
    session.scalars.assert_awaited_once()


async def test_resolve_many_returns_empty_without_database_access() -> None:
    session = _session_returning()

    assert await SqlAlchemyValuationPolicyAssignmentResolver(session).resolve_many([]) == {}

    session.scalars.assert_not_awaited()


async def test_resolve_many_rejects_unbounded_batches_before_database_access() -> None:
    session = _session_returning()
    requests = [_request(security_id=f"BOND-{index:04d}") for index in range(501)]

    with pytest.raises(ValueError, match="exceeds 500"):
        await SqlAlchemyValuationPolicyAssignmentResolver(session).resolve_many(requests)

    session.scalars.assert_not_awaited()


def test_authority_request_rejects_datetime_as_business_date() -> None:
    with pytest.raises(TypeError, match="exact date"):
        ValuationPolicyAuthorityRequest(
            scope=_request().scope,
            valuation_date=datetime(2026, 7, 19, tzinfo=UTC),  # type: ignore[arg-type]
        )
