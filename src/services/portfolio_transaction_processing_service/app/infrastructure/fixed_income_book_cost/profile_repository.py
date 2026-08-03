"""SQLAlchemy adapter for immutable lot amortized-cost profile ledgers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import date, datetime

from portfolio_common.database_models import (
    LotAmortizedCostPeriodRecord,
    LotAmortizedCostProfileRecord,
)
from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
    calculation_lineage_from_payload,
)
from sqlalchemy import select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.fixed_income_book_cost import (
    AmortizedCostDirection,
    AmortizedCostEligibilityReason,
    AmortizedCostProfileStatus,
    LotAmortizedCostPeriodLedgerEntry,
    LotAmortizedCostProfileVersion,
    LotBookCostAuthorityScope,
    lot_amortized_cost_profile_id,
)
from ...ports.fixed_income_book_cost import (
    EffectiveLotAmortizedCostProfileRequest,
    LotAmortizedCostProfileAppendOutcome,
    LotAmortizedCostProfileHead,
)


class ConflictingLotAmortizedCostProfileError(ValueError):
    """Raised when an immutable profile identity is reused with different content."""


def lot_amortized_cost_profile_lock_key(profile_id: str) -> int:
    """Return a stable signed PostgreSQL advisory-lock key for one profile stream."""

    if not isinstance(profile_id, str) or not profile_id.strip():
        raise ValueError("profile_id must be a nonblank string")
    digest = hashlib.blake2b(
        f"lot-amortized-cost-profile:{profile_id.strip()}".encode(),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


async def acquire_lot_amortized_cost_profile_lock(
    session: AsyncSession,
    scope: LotBookCostAuthorityScope,
) -> None:
    """Fence profile materialization and authority writes for one exact lot scope."""

    _require_scope(scope)
    lock_key = lot_amortized_cost_profile_lock_key(lot_amortized_cost_profile_id(scope))
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)").bindparams(lock_key=lock_key)
    )


class SqlAlchemyLotAmortizedCostProfileRepository:
    """Store profile headers and normalized periods in the caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire_materialization_lock(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> None:
        """Serialize one profile stream for the lifetime of the caller transaction."""

        await acquire_lot_amortized_cost_profile_lock(self._session, scope)

    async def latest_head(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> LotAmortizedCostProfileHead | None:
        """Load minimal current-version evidence after exact-scope filtering."""

        record = await self._latest_record(scope)
        if record is None:
            return None
        return LotAmortizedCostProfileHead(
            profile_id=record.profile_id,
            profile_version=record.profile_version,
            profile_content_hash=record.profile_content_hash,
            authority_content_hash=record.authority_content_hash,
        )

    async def latest_verified_head(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> LotAmortizedCostProfileHead | None:
        """Load and hash-verify the complete latest profile before projecting its head."""

        profile = await self.latest(scope)
        if profile is None:
            return None
        return LotAmortizedCostProfileHead(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            profile_content_hash=profile.content_hash(),
            authority_content_hash=profile.authority_content_hash,
        )

    async def latest_verified_head_for_effective_date(
        self,
        scope: LotBookCostAuthorityScope,
        *,
        effective_date: date,
    ) -> LotAmortizedCostProfileHead | None:
        """Verify and project the latest decision at one exact effective boundary."""

        _require_scope(scope)
        _require_effective_date(effective_date)
        statement = (
            select(LotAmortizedCostProfileRecord)
            .where(
                *_scope_predicates(scope),
                LotAmortizedCostProfileRecord.effective_date == effective_date,
            )
            .order_by(LotAmortizedCostProfileRecord.profile_version.desc())
            .limit(1)
        )
        record = (await self._session.scalars(statement)).first()
        if record is None:
            return None
        profile = await self._profile_from_record(record)
        return LotAmortizedCostProfileHead(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            profile_content_hash=profile.content_hash(),
            authority_content_hash=profile.authority_content_hash,
        )

    async def effective_boundaries_from(
        self,
        scope: LotBookCostAuthorityScope,
        *,
        effective_date: date,
    ) -> tuple[date, ...]:
        """Return distinct persisted decision boundaries affected by a correction."""

        _require_scope(scope)
        _require_effective_date(effective_date)
        statement = (
            select(LotAmortizedCostProfileRecord.effective_date)
            .where(
                *_scope_predicates(scope),
                LotAmortizedCostProfileRecord.effective_date >= effective_date,
            )
            .distinct()
            .order_by(LotAmortizedCostProfileRecord.effective_date.asc())
        )
        return tuple((await self._session.scalars(statement)).all())

    async def append(
        self,
        profile: LotAmortizedCostProfileVersion,
    ) -> LotAmortizedCostProfileAppendOutcome:
        """Append one profile version with one period bulk insert and no eager commit."""

        if not isinstance(profile, LotAmortizedCostProfileVersion):
            raise TypeError("profile must be a LotAmortizedCostProfileVersion")
        if profile.profile_id != lot_amortized_cost_profile_id(profile.scope):
            raise ValueError("profile_id does not match the exact source-lot scope")

        await self.acquire_materialization_lock(profile.scope)
        profile_hash = profile.content_hash()
        existing = await self._record_for_identity(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
        )
        if existing is not None:
            persisted = await self._profile_from_record(existing)
            if persisted == profile and existing.profile_content_hash == profile_hash:
                return LotAmortizedCostProfileAppendOutcome.UNCHANGED
            raise ConflictingLotAmortizedCostProfileError(
                "profile identity already exists with different immutable content"
            )
        latest = await self.latest_head(profile.scope)
        expected_version = 1 if latest is None else latest.profile_version + 1
        if profile.profile_version != expected_version:
            raise ConflictingLotAmortizedCostProfileError(
                f"profile_version must append contiguously at {expected_version}"
            )
        insert_result = await self._session.execute(
            pg_insert(LotAmortizedCostProfileRecord)
            .values(**_profile_values(profile, profile_hash=profile_hash))
            .on_conflict_do_nothing(constraint="uq_lot_amort_profile_version")
            .returning(LotAmortizedCostProfileRecord.id)
        )
        if insert_result.scalar_one_or_none() is None:
            return await self._classify_conflicting_insert(profile, profile_hash=profile_hash)
        if profile.periods:
            await self._session.execute(
                pg_insert(LotAmortizedCostPeriodRecord).values(
                    [_period_values(period) for period in profile.periods]
                )
            )
        return LotAmortizedCostProfileAppendOutcome.APPENDED

    async def latest(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> LotAmortizedCostProfileVersion | None:
        """Load the highest append version for one exact source-lot scope."""

        record = await self._latest_record(scope)
        return await self._profile_from_record(record) if record is not None else None

    async def effective_as_of(
        self,
        scope: LotBookCostAuthorityScope,
        *,
        effective_date: date,
    ) -> LotAmortizedCostProfileVersion | None:
        """Load the latest append effective on or before a governed business date."""

        _require_scope(scope)
        _require_effective_date(effective_date)
        statement = (
            select(LotAmortizedCostProfileRecord)
            .where(
                *_scope_predicates(scope),
                LotAmortizedCostProfileRecord.effective_date <= effective_date,
            )
            .order_by(
                LotAmortizedCostProfileRecord.effective_date.desc(),
                LotAmortizedCostProfileRecord.profile_version.desc(),
            )
            .limit(1)
        )
        record = (await self._session.scalars(statement)).first()
        return await self._profile_from_record(record) if record is not None else None

    async def effective_as_of_many(
        self,
        requests: Sequence[EffectiveLotAmortizedCostProfileRequest],
    ) -> dict[EffectiveLotAmortizedCostProfileRequest, LotAmortizedCostProfileVersion]:
        """Load many effective profiles in one header and one period query."""

        normalized_requests = tuple(dict.fromkeys(requests))
        if not normalized_requests:
            return {}
        for request in normalized_requests:
            if not isinstance(request, EffectiveLotAmortizedCostProfileRequest):
                raise TypeError(
                    "requests must contain EffectiveLotAmortizedCostProfileRequest values"
                )

        scope_keys = tuple(dict.fromkeys(request.scope.key for request in normalized_requests))
        latest_requested_date = max(request.effective_date for request in normalized_requests)
        records = (
            await self._session.scalars(
                select(LotAmortizedCostProfileRecord).where(
                    tuple_(
                        LotAmortizedCostProfileRecord.tenant_id,
                        LotAmortizedCostProfileRecord.legal_book_id,
                        LotAmortizedCostProfileRecord.portfolio_id,
                        LotAmortizedCostProfileRecord.security_id,
                        LotAmortizedCostProfileRecord.lot_id,
                    ).in_(scope_keys),
                    LotAmortizedCostProfileRecord.effective_date <= latest_requested_date,
                )
            )
        ).all()
        records_by_scope: dict[
            tuple[str, str, str, str, str], list[LotAmortizedCostProfileRecord]
        ] = {}
        for record in records:
            records_by_scope.setdefault(_record_scope_key(record), []).append(record)

        selected: dict[EffectiveLotAmortizedCostProfileRequest, LotAmortizedCostProfileRecord] = {}
        for request in normalized_requests:
            eligible = (
                record
                for record in records_by_scope.get(request.scope.key, ())
                if record.effective_date <= request.effective_date
            )
            record = max(
                eligible,
                key=lambda candidate: (candidate.effective_date, candidate.profile_version),
                default=None,
            )
            if record is not None:
                selected[request] = record
        if not selected:
            return {}

        selected_identities = tuple(
            dict.fromkeys(
                (record.profile_id, record.profile_version) for record in selected.values()
            )
        )
        period_records = (
            await self._session.scalars(
                select(LotAmortizedCostPeriodRecord)
                .where(
                    tuple_(
                        LotAmortizedCostPeriodRecord.profile_id,
                        LotAmortizedCostPeriodRecord.profile_version,
                    ).in_(selected_identities)
                )
                .order_by(
                    LotAmortizedCostPeriodRecord.profile_id.asc(),
                    LotAmortizedCostPeriodRecord.profile_version.asc(),
                    LotAmortizedCostPeriodRecord.period_ordinal.asc(),
                )
            )
        ).all()
        periods_by_identity: dict[tuple[str, int], list[LotAmortizedCostPeriodRecord]] = {}
        for period in period_records:
            periods_by_identity.setdefault((period.profile_id, period.profile_version), []).append(
                period
            )
        return {
            request: _profile_from_record_and_periods(
                record,
                periods_by_identity.get((record.profile_id, record.profile_version), ()),
            )
            for request, record in selected.items()
        }

    async def _classify_conflicting_insert(
        self,
        profile: LotAmortizedCostProfileVersion,
        *,
        profile_hash: str,
    ) -> LotAmortizedCostProfileAppendOutcome:
        existing = await self._record_for_identity(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
        )
        if existing is not None:
            persisted = await self._profile_from_record(existing)
            if persisted == profile and existing.profile_content_hash == profile_hash:
                return LotAmortizedCostProfileAppendOutcome.UNCHANGED
        raise ConflictingLotAmortizedCostProfileError(
            "profile identity already exists with different immutable content"
        )

    async def _latest_record(
        self,
        scope: LotBookCostAuthorityScope,
    ) -> LotAmortizedCostProfileRecord | None:
        _require_scope(scope)
        statement = (
            select(LotAmortizedCostProfileRecord)
            .where(*_scope_predicates(scope))
            .order_by(LotAmortizedCostProfileRecord.profile_version.desc())
            .limit(1)
        )
        return (await self._session.scalars(statement)).first()

    async def _record_for_identity(
        self,
        *,
        profile_id: str,
        profile_version: int,
    ) -> LotAmortizedCostProfileRecord | None:
        return (
            await self._session.scalars(
                select(LotAmortizedCostProfileRecord).where(
                    LotAmortizedCostProfileRecord.profile_id == profile_id,
                    LotAmortizedCostProfileRecord.profile_version == profile_version,
                )
            )
        ).first()

    async def _profile_from_record(
        self,
        record: LotAmortizedCostProfileRecord,
    ) -> LotAmortizedCostProfileVersion:
        period_records = (
            await self._session.scalars(
                select(LotAmortizedCostPeriodRecord)
                .where(
                    LotAmortizedCostPeriodRecord.profile_id == record.profile_id,
                    LotAmortizedCostPeriodRecord.profile_version == record.profile_version,
                )
                .order_by(LotAmortizedCostPeriodRecord.period_ordinal.asc())
            )
        ).all()
        return _profile_from_record_and_periods(record, period_records)


def _profile_from_record_and_periods(
    record: LotAmortizedCostProfileRecord,
    period_records: Sequence[LotAmortizedCostPeriodRecord],
) -> LotAmortizedCostProfileVersion:
    profile = LotAmortizedCostProfileVersion(
        profile_id=record.profile_id,
        profile_version=record.profile_version,
        scope=LotBookCostAuthorityScope(
            tenant_id=record.tenant_id,
            legal_book_id=record.legal_book_id,
            portfolio_id=record.portfolio_id,
            security_id=record.security_id,
            lot_id=record.lot_id,
        ),
        effective_date=record.effective_date,
        status=AmortizedCostProfileStatus(record.status),
        eligibility_reason=(
            AmortizedCostEligibilityReason(record.eligibility_reason)
            if record.eligibility_reason is not None
            else None
        ),
        policy_id=record.policy_id,
        policy_version=record.policy_version,
        schedule_version=record.schedule_version,
        currency=record.currency,
        direction=(
            AmortizedCostDirection(record.direction) if record.direction is not None else None
        ),
        initial_amortized_cost_local=record.initial_amortized_cost_local,
        redemption_value_local=record.redemption_value_local,
        final_amortized_cost_local=record.final_amortized_cost_local,
        residual_local=record.residual_local,
        authority_content_hash=record.authority_content_hash,
        source_references=_sources_from_payload(record.source_references),
        calculation_lineage=calculation_lineage_from_payload(record.calculation_lineage),
        periods=tuple(_period_from_record(period) for period in period_records),
    )
    if profile.profile_id != lot_amortized_cost_profile_id(profile.scope):
        raise ConflictingLotAmortizedCostProfileError(
            "persisted profile identity does not match its exact source-lot scope"
        )
    if profile.content_hash() != record.profile_content_hash:
        raise ConflictingLotAmortizedCostProfileError(
            "persisted profile content does not match its immutable hash"
        )
    if not _profile_record_matches(record, profile):
        raise ConflictingLotAmortizedCostProfileError(
            "persisted profile does not use its canonical representation"
        )
    return profile


def _record_scope_key(record: LotAmortizedCostProfileRecord) -> tuple[str, str, str, str, str]:
    return (
        record.tenant_id,
        record.legal_book_id,
        record.portfolio_id,
        record.security_id,
        record.lot_id,
    )


def _profile_values(
    profile: LotAmortizedCostProfileVersion,
    *,
    profile_hash: str,
) -> dict[str, object]:
    return {
        "authority_content_hash": profile.authority_content_hash,
        "calculation_lineage": (
            profile.calculation_lineage.lineage_payload()
            if profile.calculation_lineage is not None
            else None
        ),
        "currency": profile.currency,
        "direction": profile.direction.value if profile.direction is not None else None,
        "effective_date": profile.effective_date,
        "eligibility_reason": (
            profile.eligibility_reason.value if profile.eligibility_reason is not None else None
        ),
        "final_amortized_cost_local": profile.final_amortized_cost_local,
        "initial_amortized_cost_local": profile.initial_amortized_cost_local,
        "legal_book_id": profile.scope.legal_book_id,
        "lot_id": profile.scope.lot_id,
        "policy_id": profile.policy_id,
        "policy_version": profile.policy_version,
        "portfolio_id": profile.scope.portfolio_id,
        "profile_content_hash": profile_hash,
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "redemption_value_local": profile.redemption_value_local,
        "residual_local": profile.residual_local,
        "schedule_version": profile.schedule_version,
        "security_id": profile.scope.security_id,
        "source_references": [_source_payload(source) for source in profile.source_references],
        "status": profile.status.value,
        "tenant_id": profile.scope.tenant_id,
    }


def _profile_record_matches(
    record: LotAmortizedCostProfileRecord,
    profile: LotAmortizedCostProfileVersion,
) -> bool:
    expected = _profile_values(profile, profile_hash=profile.content_hash())
    return all(getattr(record, key) == value for key, value in expected.items())


def _period_values(period: LotAmortizedCostPeriodLedgerEntry) -> dict[str, object]:
    return {
        "amortization_amount_local": period.amortization_amount_local,
        "begin_amortized_cost_local": period.begin_amortized_cost_local,
        "calculation_output_hash": period.calculation_output_hash,
        "cash_coupon_local": period.cash_coupon_local,
        "end_amortized_cost_local": period.end_amortized_cost_local,
        "interest_income_local": period.interest_income_local,
        "period_content_hash": period.content_hash(),
        "period_end_date": period.period_end_date,
        "period_ordinal": period.period_ordinal,
        "period_rate": period.period_rate,
        "period_start_date": period.period_start_date,
        "profile_id": period.profile_id,
        "profile_version": period.profile_version,
        "rounding_adjustment_local": period.rounding_adjustment_local,
        "year_fraction": period.year_fraction,
    }


def _period_from_record(
    record: LotAmortizedCostPeriodRecord,
) -> LotAmortizedCostPeriodLedgerEntry:
    period = LotAmortizedCostPeriodLedgerEntry(
        profile_id=record.profile_id,
        profile_version=record.profile_version,
        period_ordinal=record.period_ordinal,
        period_start_date=record.period_start_date,
        period_end_date=record.period_end_date,
        year_fraction=record.year_fraction,
        period_rate=record.period_rate,
        begin_amortized_cost_local=record.begin_amortized_cost_local,
        interest_income_local=record.interest_income_local,
        cash_coupon_local=record.cash_coupon_local,
        amortization_amount_local=record.amortization_amount_local,
        end_amortized_cost_local=record.end_amortized_cost_local,
        rounding_adjustment_local=record.rounding_adjustment_local,
        calculation_output_hash=record.calculation_output_hash,
    )
    if period.content_hash() != record.period_content_hash:
        raise ConflictingLotAmortizedCostProfileError(
            "persisted period content does not match its immutable hash"
        )
    return period


def _source_payload(source: FinancialSourceReference) -> dict[str, object]:
    return {
        "observed_at": source.observed_at.isoformat(),
        "source_content_hash": source.source_content_hash,
        "source_record_id": source.source_record_id,
        "source_revision": source.source_revision,
        "source_system": source.source_system,
    }


def _sources_from_payload(payload: object) -> tuple[FinancialSourceReference, ...]:
    if not isinstance(payload, list):
        raise TypeError("profile source_references must be an array")
    return tuple(_source_from_payload(source) for source in payload)


def _source_from_payload(payload: object) -> FinancialSourceReference:
    if not isinstance(payload, Mapping):
        raise TypeError("profile source reference must be an object")
    expected_keys = {
        "observed_at",
        "source_content_hash",
        "source_record_id",
        "source_revision",
        "source_system",
    }
    if set(payload) != expected_keys:
        raise ValueError("profile source reference has an unsupported evidence shape")
    return FinancialSourceReference(
        source_system=_required_string(payload, "source_system"),
        source_record_id=_required_string(payload, "source_record_id"),
        source_revision=_required_string(payload, "source_revision"),
        source_content_hash=_required_string(payload, "source_content_hash"),
        observed_at=datetime.fromisoformat(_required_string(payload, "observed_at")),
    )


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _require_scope(scope: LotBookCostAuthorityScope) -> None:
    if not isinstance(scope, LotBookCostAuthorityScope):
        raise TypeError("scope must be a LotBookCostAuthorityScope")


def _require_effective_date(effective_date: date) -> None:
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date")


def _scope_predicates(scope: LotBookCostAuthorityScope) -> tuple[object, ...]:
    return (
        LotAmortizedCostProfileRecord.tenant_id == scope.tenant_id,
        LotAmortizedCostProfileRecord.legal_book_id == scope.legal_book_id,
        LotAmortizedCostProfileRecord.portfolio_id == scope.portfolio_id,
        LotAmortizedCostProfileRecord.security_id == scope.security_id,
        LotAmortizedCostProfileRecord.lot_id == scope.lot_id,
    )
