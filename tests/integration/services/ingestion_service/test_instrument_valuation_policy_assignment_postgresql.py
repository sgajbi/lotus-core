"""PostgreSQL proof for serialized valuation-policy assignment authority."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import (
    Instrument,
    InstrumentValuationPolicyAssignmentRecord,
)
from portfolio_common.domain.valuation.assignments import (
    OverlappingValuationPolicyAssignmentError,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)

pytestmark = pytest.mark.asyncio

SECURITY_ID = "ISSUE788_VAL_POLICY_BOND"
ISIN = "XS7880000001"
TENANT_ID = "ISSUE788_TENANT"
LEGAL_BOOK_ID = "ISSUE788_LEGAL_BOOK"


def _async_database_url() -> str:
    database_url = (
        os.getenv("LOTUS_VALUATION_POLICY_POSTGRESQL_URL")
        or os.getenv("HOST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
    )
    if not database_url:
        pytest.skip("PostgreSQL URL is required for the valuation-policy integration proof")
    assert database_url is not None
    return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _assignment(
    *,
    source_record_id: str,
    assignment_version: int = 1,
    assignment_status: str = "ACTIVE",
    source_revision: str = "rev-001",
    valid_from: date = date(2026, 1, 1),
) -> dict[str, object]:
    return {
        "tenant_id": TENANT_ID,
        "legal_book_id": LEGAL_BOOK_ID,
        "security_id": SECURITY_ID,
        "policy_id": "CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL",
        "policy_version": 1,
        "valid_from": valid_from,
        "valid_to": None,
        "assignment_status": assignment_status,
        "assignment_version": assignment_version,
        "source_system": "security_master",
        "source_record_id": source_record_id,
        "source_revision": source_revision,
        "observed_at": datetime(2026, 7, assignment_version, 9, tzinfo=UTC),
        "assignment_reason": "Clean-price fixed-rate bond treatment.",
    }


async def test_assignment_write_guard_rejects_durable_overlap_and_accepts_retirement() -> None:
    engine = create_async_engine(_async_database_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with sessions() as session:
            await session.execute(
                delete(InstrumentValuationPolicyAssignmentRecord).where(
                    InstrumentValuationPolicyAssignmentRecord.security_id == SECURITY_ID
                )
            )
            await session.execute(delete(Instrument).where(Instrument.security_id == SECURITY_ID))
            session.add(
                Instrument(
                    security_id=SECURITY_ID,
                    name="Issue 788 valuation policy bond",
                    isin=ISIN,
                    currency="USD",
                    product_type="BOND",
                    asset_class="FIXED_INCOME",
                )
            )
            await session.commit()

            ingestion = ReferenceDataIngestionService(session)
            await ingestion.upsert_instrument_valuation_policy_assignments(
                [_assignment(source_record_id="PRIMARY")]
            )

            with pytest.raises(
                OverlappingValuationPolicyAssignmentError,
                match="windows overlap",
            ):
                await ingestion.upsert_instrument_valuation_policy_assignments(
                    [
                        _assignment(
                            source_record_id="SECONDARY",
                            valid_from=date(2026, 7, 1),
                        )
                    ]
                )

            assert (
                await session.scalar(
                    select(func.count(InstrumentValuationPolicyAssignmentRecord.id)).where(
                        InstrumentValuationPolicyAssignmentRecord.security_id == SECURITY_ID
                    )
                )
                == 1
            )

            await ingestion.upsert_instrument_valuation_policy_assignments(
                [
                    _assignment(
                        source_record_id="PRIMARY",
                        assignment_version=2,
                        assignment_status="RETIRED",
                        source_revision="rev-002",
                    ),
                    _assignment(
                        source_record_id="SECONDARY",
                        source_revision="rev-001-secondary",
                        valid_from=date(2026, 7, 1),
                    ),
                ]
            )

            rows = list(
                (
                    await session.scalars(
                        select(InstrumentValuationPolicyAssignmentRecord)
                        .where(InstrumentValuationPolicyAssignmentRecord.security_id == SECURITY_ID)
                        .order_by(
                            InstrumentValuationPolicyAssignmentRecord.source_record_id,
                            InstrumentValuationPolicyAssignmentRecord.assignment_version,
                        )
                    )
                ).all()
            )
            assert [
                (row.source_record_id, row.assignment_version, row.assignment_status)
                for row in rows
            ] == [
                ("PRIMARY", 1, "ACTIVE"),
                ("PRIMARY", 2, "RETIRED"),
                ("SECONDARY", 1, "ACTIVE"),
            ]
    finally:
        async with sessions() as session:
            await session.execute(
                delete(InstrumentValuationPolicyAssignmentRecord).where(
                    InstrumentValuationPolicyAssignmentRecord.security_id == SECURITY_ID
                )
            )
            await session.execute(delete(Instrument).where(Instrument.security_id == SECURITY_ID))
            await session.commit()
        await engine.dispose()


async def test_concurrent_assignment_writers_serialize_without_deadlock() -> None:
    engine = create_async_engine(_async_database_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with sessions() as session:
            await session.execute(
                delete(InstrumentValuationPolicyAssignmentRecord).where(
                    InstrumentValuationPolicyAssignmentRecord.security_id == SECURITY_ID
                )
            )
            await session.execute(delete(Instrument).where(Instrument.security_id == SECURITY_ID))
            session.add(
                Instrument(
                    security_id=SECURITY_ID,
                    name="Issue 788 concurrent valuation policy bond",
                    isin=ISIN,
                    currency="USD",
                    product_type="BOND",
                    asset_class="FIXED_INCOME",
                )
            )
            await session.commit()

        async def _ingest(source_record_id: str) -> None:
            async with sessions() as session:
                await ReferenceDataIngestionService(
                    session
                ).upsert_instrument_valuation_policy_assignments(
                    [_assignment(source_record_id=source_record_id)]
                )

        results = await asyncio.wait_for(
            asyncio.gather(
                _ingest("CONCURRENT-A"),
                _ingest("CONCURRENT-B"),
                return_exceptions=True,
            ),
            timeout=10,
        )

        assert sum(result is None for result in results) == 1
        failures = [result for result in results if result is not None]
        assert len(failures) == 1
        assert isinstance(failures[0], OverlappingValuationPolicyAssignmentError)

        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count(InstrumentValuationPolicyAssignmentRecord.id)).where(
                        InstrumentValuationPolicyAssignmentRecord.security_id == SECURITY_ID
                    )
                )
                == 1
            )
    finally:
        async with sessions() as session:
            await session.execute(
                delete(InstrumentValuationPolicyAssignmentRecord).where(
                    InstrumentValuationPolicyAssignmentRecord.security_id == SECURITY_ID
                )
            )
            await session.execute(delete(Instrument).where(Instrument.security_id == SECURITY_ID))
            await session.commit()
        await engine.dispose()
