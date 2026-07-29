"""SQLAlchemy persistence and reconstruction for valuation receipts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    DailyPositionValuationReceiptRecord,
)
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    FinancialSourceReference,
    NumericOutputPolicyLineage,
)
from portfolio_common.domain.valuation import (
    MarketPriceQuoteBasis,
    ValuationCalculationReceipt,
    ValuationReceiptSupportability,
    ValuationSnapshotIdentity,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyValuationReceiptRepository:
    """Store complete receipts atomically with caller-owned snapshot transactions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert(
        self,
        *,
        snapshot_id: int,
        receipt: ValuationCalculationReceipt,
    ) -> ValuationCalculationReceipt:
        if not isinstance(snapshot_id, int) or isinstance(snapshot_id, bool) or snapshot_id < 1:
            raise ValueError("snapshot_id must be a positive integer")
        values = _record_values(snapshot_id=snapshot_id, receipt=receipt)
        record = DailyPositionValuationReceiptRecord
        statement = (
            pg_insert(record)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[record.snapshot_id],
                set_={key: value for key, value in values.items() if key != "snapshot_id"},
            )
            .returning(record)
        )
        persisted = (await self._db.scalars(statement)).one()
        return _receipt_from_record(persisted, receipt.snapshot_identity)

    async def fetch_many(
        self,
        snapshot_ids: Sequence[int],
    ) -> Mapping[int, ValuationCalculationReceipt]:
        normalized_ids = sorted(set(snapshot_ids))
        if not normalized_ids:
            return {}
        if any(
            not isinstance(snapshot_id, int) or isinstance(snapshot_id, bool) or snapshot_id < 1
            for snapshot_id in normalized_ids
        ):
            raise ValueError("snapshot_ids must contain only positive integers")
        record = DailyPositionValuationReceiptRecord
        snapshot = DailyPositionSnapshot
        statement = (
            select(record, snapshot)
            .join(snapshot, snapshot.id == record.snapshot_id)
            .where(record.snapshot_id.in_(normalized_ids))
            .order_by(record.snapshot_id.asc())
        )
        rows = (await self._db.execute(statement)).all()
        return {
            persisted_receipt.snapshot_id: _receipt_from_record(
                persisted_receipt,
                ValuationSnapshotIdentity(
                    portfolio_id=persisted_snapshot.portfolio_id,
                    security_id=persisted_snapshot.security_id,
                    valuation_date=persisted_snapshot.date,
                    epoch=persisted_snapshot.epoch,
                ),
            )
            for persisted_receipt, persisted_snapshot in rows
        }


def _record_values(
    *,
    snapshot_id: int,
    receipt: ValuationCalculationReceipt,
) -> dict[str, object]:
    return {
        "assignment_content_hash": receipt.assignment_content_hash,
        "assignment_version": receipt.assignment_version,
        "calculation_lineage": (
            receipt.calculation_lineage.lineage_payload()
            if receipt.calculation_lineage is not None
            else None
        ),
        "market_price_source": _source_payload(receipt.market_price_source),
        "policy_assignment_source": _source_payload(receipt.policy_assignment_source),
        "policy_id": receipt.policy_id,
        "policy_version": receipt.policy_version,
        "price_fact_content_hash": receipt.price_fact_content_hash,
        "price_fact_version": receipt.price_fact_version,
        "quote_basis": receipt.quote_basis.value if receipt.quote_basis is not None else None,
        "receipt_hash": receipt.receipt_hash,
        "snapshot_id": snapshot_id,
        "supportability": receipt.supportability.value,
        "supportability_reasons": list(receipt.supportability_reasons),
    }


def _source_payload(source: FinancialSourceReference | None) -> dict[str, object] | None:
    if source is None:
        return None
    return {
        "observed_at": source.observed_at.isoformat(),
        "source_content_hash": source.source_content_hash,
        "source_record_id": source.source_record_id,
        "source_revision": source.source_revision,
        "source_system": source.source_system,
    }


def _receipt_from_record(
    record: DailyPositionValuationReceiptRecord,
    snapshot_identity: ValuationSnapshotIdentity,
) -> ValuationCalculationReceipt:
    return ValuationCalculationReceipt(
        snapshot_identity=snapshot_identity,
        supportability=ValuationReceiptSupportability(record.supportability),
        supportability_reasons=tuple(record.supportability_reasons),
        policy_id=record.policy_id,
        policy_version=record.policy_version,
        assignment_version=record.assignment_version,
        assignment_content_hash=record.assignment_content_hash,
        policy_assignment_source=_source_from_payload(record.policy_assignment_source),
        quote_basis=(
            MarketPriceQuoteBasis(record.quote_basis) if record.quote_basis is not None else None
        ),
        price_fact_version=record.price_fact_version,
        price_fact_content_hash=record.price_fact_content_hash,
        market_price_source=_source_from_payload(record.market_price_source),
        calculation_lineage=_lineage_from_payload(record.calculation_lineage),
        receipt_hash=record.receipt_hash,
    )


def _source_from_payload(payload: object) -> FinancialSourceReference | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise TypeError("valuation receipt source payload must be an object")
    return FinancialSourceReference(
        source_system=_required_string(payload, "source_system"),
        source_record_id=_required_string(payload, "source_record_id"),
        source_revision=_required_string(payload, "source_revision"),
        source_content_hash=_required_string(payload, "source_content_hash"),
        observed_at=datetime.fromisoformat(_required_string(payload, "observed_at")),
    )


def _lineage_from_payload(payload: object) -> CalculationLineage | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise TypeError("valuation receipt calculation_lineage must be an object")
    numeric_payload = payload.get("numeric_output_policy")
    numeric_policy = None
    if numeric_payload is not None:
        if not isinstance(numeric_payload, dict):
            raise TypeError("numeric_output_policy must be an object")
        numeric_policy = NumericOutputPolicyLineage(
            name=_required_string(numeric_payload, "name"),
            version=_required_string(numeric_payload, "version"),
            precision=_required_int(numeric_payload, "precision"),
            scale=_required_int(numeric_payload, "scale"),
            working_precision=_required_int(numeric_payload, "working_precision"),
            rounding=_required_string(numeric_payload, "rounding"),
        )
    return CalculationLineage(
        algorithm_id=_required_string(payload, "algorithm_id"),
        algorithm_version=_required_int(payload, "algorithm_version"),
        intermediate_precision=_required_int(payload, "intermediate_precision"),
        input_content_hash=_required_string(payload, "input_content_hash"),
        calculation_content_hash=_required_string(payload, "calculation_content_hash"),
        output_content_hash=_required_string(payload, "output_content_hash"),
        numeric_output_policy=numeric_policy,
    )


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an integer")
    return value
