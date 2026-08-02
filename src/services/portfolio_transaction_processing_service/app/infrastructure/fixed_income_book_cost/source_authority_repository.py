"""SQLAlchemy adapter for source-versioned lot amortized-cost authority."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal, DecimalException
from enum import StrEnum
from typing import cast

from portfolio_common.database_models import LotAmortizedCostAuthorityRecord
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.fixed_income_book_cost import (
    AmortizationPeriodInput,
    AmortizedCostAssignmentStatus,
    AmortizedCostSourceFactStatus,
    AmortizedCostSourceMetadata,
    DiscountOriginClassification,
    LotAmortizationScheduleFact,
    LotAmortizedCostBasisFact,
    LotAmortizedCostPolicyAssignment,
    LotBookCostAuthorityScope,
    LotEffectiveYieldFact,
    YieldApplicationConvention,
)
from ...ports.fixed_income_book_cost import (
    LotAmortizedCostAuthority,
    LotAmortizedCostAuthorityAppendOutcome,
    LotAmortizedCostAuthorityBundle,
)


class ConflictingLotAmortizedCostAuthorityError(ValueError):
    """Raised when one immutable source version is reused with different content."""


class _AuthorityType(StrEnum):
    POLICY_ASSIGNMENT = "POLICY_ASSIGNMENT"
    CLEAN_COST_BASIS = "CLEAN_COST_BASIS"
    AMORTIZATION_SCHEDULE = "AMORTIZATION_SCHEDULE"
    EFFECTIVE_YIELD = "EFFECTIVE_YIELD"


_PAYLOAD_KEYS = {
    _AuthorityType.POLICY_ASSIGNMENT: frozenset(
        {"assignment_reason", "policy_id", "policy_version"}
    ),
    _AuthorityType.CLEAN_COST_BASIS: frozenset(
        {
            "currency",
            "discount_origin",
            "fees_in_basis_local",
            "initial_clean_cost_local",
            "redemption_value_local",
        }
    ),
    _AuthorityType.AMORTIZATION_SCHEDULE: frozenset(
        {
            "periods",
            "schedule_version",
            "year_fraction_method_id",
            "year_fraction_method_version",
        }
    ),
    _AuthorityType.EFFECTIVE_YIELD: frozenset({"annual_yield", "yield_application_convention"}),
}
_PERIOD_KEYS = frozenset(
    {
        "cash_coupon_local",
        "period_end_date",
        "period_start_date",
        "supplied_period_rate",
        "year_fraction",
    }
)


class SqlAlchemyLotAmortizedCostAuthorityRepository:
    """Persist immutable source versions in the caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        authority: LotAmortizedCostAuthority,
    ) -> LotAmortizedCostAuthorityAppendOutcome:
        values = _authority_values(authority)
        await self._acquire_source_lock(values)
        existing = await self._record_for_identity(values)
        if existing is not None:
            if _record_matches(existing, values):
                return LotAmortizedCostAuthorityAppendOutcome.UNCHANGED
            raise ConflictingLotAmortizedCostAuthorityError(
                "amortized-cost authority source version already exists with different content"
            )
        latest_version = await self._latest_source_version(values)
        if latest_version is not None and cast(int, values["source_version"]) <= latest_version:
            raise ConflictingLotAmortizedCostAuthorityError(
                "amortized-cost authority source version must increase monotonically"
            )
        inserted = await self._session.execute(
            pg_insert(LotAmortizedCostAuthorityRecord)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_lot_amort_authority_source_version")
            .returning(LotAmortizedCostAuthorityRecord.id)
        )
        if inserted.scalar_one_or_none() is not None:
            return LotAmortizedCostAuthorityAppendOutcome.APPENDED
        existing = await self._record_for_identity(values)
        if existing is not None and _record_matches(existing, values):
            return LotAmortizedCostAuthorityAppendOutcome.UNCHANGED
        raise ConflictingLotAmortizedCostAuthorityError(
            "amortized-cost authority source version already exists with different content"
        )

    async def _acquire_source_lock(self, values: dict[str, object]) -> None:
        identity = ":".join(
            str(values[key])
            for key in (
                "authority_type",
                "tenant_id",
                "legal_book_id",
                "portfolio_id",
                "security_id",
                "lot_id",
                "source_system",
                "source_record_id",
            )
        )
        digest = hashlib.blake2b(
            f"lot-amortized-cost-authority:{identity}".encode(),
            digest_size=8,
        ).digest()
        lock_key = int.from_bytes(digest, byteorder="big", signed=True)
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)").bindparams(lock_key=lock_key)
        )

    async def _latest_source_version(self, values: dict[str, object]) -> int | None:
        record = LotAmortizedCostAuthorityRecord
        latest = await self._session.scalar(
            select(func.max(record.source_version)).where(
                record.authority_type == values["authority_type"],
                record.tenant_id == values["tenant_id"],
                record.legal_book_id == values["legal_book_id"],
                record.portfolio_id == values["portfolio_id"],
                record.security_id == values["security_id"],
                record.lot_id == values["lot_id"],
                record.source_system == values["source_system"],
                record.source_record_id == values["source_record_id"],
            )
        )
        return cast(int | None, latest)

    async def load(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> LotAmortizedCostAuthorityBundle:
        if not isinstance(scope, LotBookCostAuthorityScope):
            raise TypeError("scope must be a LotBookCostAuthorityScope")
        records = (
            await self._session.scalars(
                select(LotAmortizedCostAuthorityRecord)
                .where(*_scope_predicates(scope))
                .order_by(
                    LotAmortizedCostAuthorityRecord.authority_type,
                    LotAmortizedCostAuthorityRecord.source_system,
                    LotAmortizedCostAuthorityRecord.source_record_id,
                    LotAmortizedCostAuthorityRecord.source_version,
                )
            )
        ).all()
        assignments: list[LotAmortizedCostPolicyAssignment] = []
        basis_facts: list[LotAmortizedCostBasisFact] = []
        schedule_facts: list[LotAmortizationScheduleFact] = []
        yield_facts: list[LotEffectiveYieldFact] = []
        for record in records:
            authority = _authority_from_record(record)
            if isinstance(authority, LotAmortizedCostPolicyAssignment):
                assignments.append(authority)
            elif isinstance(authority, LotAmortizedCostBasisFact):
                basis_facts.append(authority)
            elif isinstance(authority, LotAmortizationScheduleFact):
                schedule_facts.append(authority)
            else:
                yield_facts.append(cast(LotEffectiveYieldFact, authority))
        return LotAmortizedCostAuthorityBundle(
            assignments=tuple(assignments),
            basis_facts=tuple(basis_facts),
            schedule_facts=tuple(schedule_facts),
            yield_facts=tuple(yield_facts),
        )

    async def _record_for_identity(
        self,
        values: dict[str, object],
    ) -> LotAmortizedCostAuthorityRecord | None:
        return (
            await self._session.scalars(
                select(LotAmortizedCostAuthorityRecord).where(
                    LotAmortizedCostAuthorityRecord.authority_type == values["authority_type"],
                    LotAmortizedCostAuthorityRecord.tenant_id == values["tenant_id"],
                    LotAmortizedCostAuthorityRecord.legal_book_id == values["legal_book_id"],
                    LotAmortizedCostAuthorityRecord.portfolio_id == values["portfolio_id"],
                    LotAmortizedCostAuthorityRecord.security_id == values["security_id"],
                    LotAmortizedCostAuthorityRecord.lot_id == values["lot_id"],
                    LotAmortizedCostAuthorityRecord.source_system == values["source_system"],
                    LotAmortizedCostAuthorityRecord.source_record_id == values["source_record_id"],
                    LotAmortizedCostAuthorityRecord.source_version == values["source_version"],
                )
            )
        ).first()


def _authority_values(authority: LotAmortizedCostAuthority) -> dict[str, object]:
    if isinstance(authority, LotAmortizedCostPolicyAssignment):
        authority_type = _AuthorityType.POLICY_ASSIGNMENT
        source_version = authority.assignment_version
        source_system = authority.source_system
        source_record_id = authority.source_record_id
        source_revision = authority.source_revision
        observed_at = authority.observed_at
        status = authority.assignment_status.value
        payload: dict[str, object] = {
            "assignment_reason": authority.assignment_reason,
            "policy_id": authority.policy_id,
            "policy_version": authority.policy_version,
        }
        content_hash = authority.content_hash()
    elif isinstance(authority, LotAmortizedCostBasisFact):
        authority_type = _AuthorityType.CLEAN_COST_BASIS
        source_version, source_system, source_record_id, source_revision, observed_at = (
            _source_columns(authority.source)
        )
        status = authority.fact_status.value
        payload = {
            "currency": authority.currency,
            "discount_origin": authority.discount_origin.value,
            "fees_in_basis_local": str(authority.fees_in_basis_local),
            "initial_clean_cost_local": str(authority.initial_clean_cost_local),
            "redemption_value_local": str(authority.redemption_value_local),
        }
        content_hash = authority.content_hash()
    elif isinstance(authority, LotAmortizationScheduleFact):
        authority_type = _AuthorityType.AMORTIZATION_SCHEDULE
        source_version, source_system, source_record_id, source_revision, observed_at = (
            _source_columns(authority.source)
        )
        status = authority.fact_status.value
        payload = {
            "periods": [
                {
                    "cash_coupon_local": str(period.cash_coupon_local),
                    "period_end_date": period.period_end_date.isoformat(),
                    "period_start_date": period.period_start_date.isoformat(),
                    "supplied_period_rate": (
                        str(period.supplied_period_rate)
                        if period.supplied_period_rate is not None
                        else None
                    ),
                    "year_fraction": str(period.year_fraction),
                }
                for period in authority.periods
            ],
            "schedule_version": authority.schedule_version,
            "year_fraction_method_id": authority.year_fraction_method_id,
            "year_fraction_method_version": authority.year_fraction_method_version,
        }
        content_hash = authority.content_hash()
    elif isinstance(authority, LotEffectiveYieldFact):
        authority_type = _AuthorityType.EFFECTIVE_YIELD
        source_version, source_system, source_record_id, source_revision, observed_at = (
            _source_columns(authority.source)
        )
        status = authority.fact_status.value
        payload = {
            "annual_yield": str(authority.annual_yield),
            "yield_application_convention": authority.yield_application_convention.value,
        }
        content_hash = authority.content_hash()
    else:
        raise TypeError("authority has an unsupported amortized-cost authority type")
    scope = authority.scope
    return {
        "authority_content_hash": content_hash,
        "authority_payload": payload,
        "authority_type": authority_type.value,
        "legal_book_id": scope.legal_book_id,
        "lifecycle_status": status,
        "lot_id": scope.lot_id,
        "observed_at": observed_at,
        "portfolio_id": scope.portfolio_id,
        "security_id": scope.security_id,
        "source_record_id": source_record_id,
        "source_revision": source_revision,
        "source_system": source_system,
        "source_version": source_version,
        "tenant_id": scope.tenant_id,
        "valid_from": authority.valid_from,
        "valid_to": authority.valid_to,
    }


def _authority_from_record(
    record: LotAmortizedCostAuthorityRecord,
) -> LotAmortizedCostAuthority:
    scope = LotBookCostAuthorityScope(
        tenant_id=record.tenant_id,
        legal_book_id=record.legal_book_id,
        portfolio_id=record.portfolio_id,
        security_id=record.security_id,
        lot_id=record.lot_id,
    )
    payload = record.authority_payload
    if not isinstance(payload, dict):
        raise ConflictingLotAmortizedCostAuthorityError("authority payload must be an object")
    authority_type = _AuthorityType(record.authority_type)
    _require_exact_keys(payload, _PAYLOAD_KEYS[authority_type], context="authority payload")
    if authority_type is _AuthorityType.POLICY_ASSIGNMENT:
        authority: LotAmortizedCostAuthority = LotAmortizedCostPolicyAssignment(
            scope=scope,
            policy_id=_string(payload, "policy_id"),
            policy_version=_integer(payload, "policy_version"),
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            assignment_status=AmortizedCostAssignmentStatus(record.lifecycle_status),
            assignment_version=record.source_version,
            source_system=record.source_system,
            source_record_id=record.source_record_id,
            source_revision=record.source_revision,
            observed_at=record.observed_at,
            assignment_reason=_string(payload, "assignment_reason"),
        )
    else:
        source = AmortizedCostSourceMetadata(
            source_system=record.source_system,
            source_record_id=record.source_record_id,
            source_revision=record.source_revision,
            fact_version=record.source_version,
            observed_at=record.observed_at,
        )
        common = {
            "scope": scope,
            "valid_from": record.valid_from,
            "valid_to": record.valid_to,
            "fact_status": AmortizedCostSourceFactStatus(record.lifecycle_status),
            "source": source,
        }
        if authority_type is _AuthorityType.CLEAN_COST_BASIS:
            authority = LotAmortizedCostBasisFact(
                currency=_string(payload, "currency"),
                initial_clean_cost_local=_decimal(payload, "initial_clean_cost_local"),
                fees_in_basis_local=_decimal(payload, "fees_in_basis_local"),
                redemption_value_local=_decimal(payload, "redemption_value_local"),
                discount_origin=DiscountOriginClassification(_string(payload, "discount_origin")),
                **common,
            )
        elif authority_type is _AuthorityType.AMORTIZATION_SCHEDULE:
            authority = LotAmortizationScheduleFact(
                schedule_version=_integer(payload, "schedule_version"),
                year_fraction_method_id=_string(payload, "year_fraction_method_id"),
                year_fraction_method_version=_integer(payload, "year_fraction_method_version"),
                periods=_periods(payload),
                **common,
            )
        else:
            authority = LotEffectiveYieldFact(
                annual_yield=_decimal(payload, "annual_yield"),
                yield_application_convention=YieldApplicationConvention(
                    _string(payload, "yield_application_convention")
                ),
                **common,
            )
    if authority.content_hash() != record.authority_content_hash:
        raise ConflictingLotAmortizedCostAuthorityError(
            "persisted amortized-cost authority does not match its immutable hash"
        )
    if not _record_matches(record, _authority_values(authority)):
        raise ConflictingLotAmortizedCostAuthorityError(
            "persisted amortized-cost authority does not use its canonical representation"
        )
    return authority


def _periods(payload: dict[str, object]) -> tuple[AmortizationPeriodInput, ...]:
    rows = payload.get("periods")
    if not isinstance(rows, list):
        raise TypeError("periods must be an array")
    periods: list[AmortizationPeriodInput] = []
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("period must be an object")
        _require_exact_keys(row, _PERIOD_KEYS, context="schedule period")
        supplied_rate = row.get("supplied_period_rate")
        if supplied_rate is not None and not isinstance(supplied_rate, str):
            raise ConflictingLotAmortizedCostAuthorityError(
                "schedule period supplied_period_rate must be a string or null"
            )
        periods.append(
            AmortizationPeriodInput(
                period_start_date=date.fromisoformat(_string(row, "period_start_date")),
                period_end_date=date.fromisoformat(_string(row, "period_end_date")),
                year_fraction=_decimal(row, "year_fraction"),
                cash_coupon_local=_decimal(row, "cash_coupon_local"),
                supplied_period_rate=(
                    _canonical_decimal_text(
                        supplied_rate,
                        context="schedule period supplied_period_rate",
                    )
                    if supplied_rate is not None
                    else None
                ),
            )
        )
    return tuple(periods)


def _record_matches(
    record: LotAmortizedCostAuthorityRecord,
    values: dict[str, object],
) -> bool:
    return all(getattr(record, key) == value for key, value in values.items())


def _source_columns(
    source: AmortizedCostSourceMetadata,
) -> tuple[int, str, str, str, datetime]:
    return (
        source.fact_version,
        source.source_system,
        source.source_record_id,
        source.source_revision,
        source.observed_at,
    )


def _scope_predicates(scope: LotBookCostAuthorityScope) -> tuple[object, ...]:
    record = LotAmortizedCostAuthorityRecord
    return (
        record.tenant_id == scope.tenant_id,
        record.legal_book_id == scope.legal_book_id,
        record.portfolio_id == scope.portfolio_id,
        record.security_id == scope.security_id,
        record.lot_id == scope.lot_id,
    )


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an integer")
    return value


def _decimal(payload: dict[str, object], key: str) -> Decimal:
    return _canonical_decimal_text(_string(payload, key), context=key)


def _canonical_decimal_text(value: str, *, context: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except DecimalException as exc:
        raise ConflictingLotAmortizedCostAuthorityError(
            f"{context} must use canonical decimal text"
        ) from exc
    if not parsed.is_finite() or str(parsed) != value:
        raise ConflictingLotAmortizedCostAuthorityError(
            f"{context} must use canonical decimal text"
        )
    return parsed


def _require_exact_keys(
    payload: dict[str, object],
    expected: frozenset[str],
    *,
    context: str,
) -> None:
    actual = frozenset(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unsupported = sorted(actual - expected)
        raise ConflictingLotAmortizedCostAuthorityError(
            f"{context} keys do not match the immutable schema; "
            f"missing={missing}, unsupported={unsupported}"
        )
