"""Append immutable classification source versions within the reference transaction."""

import json
from datetime import UTC, datetime

from portfolio_common.api_contract.classification_history import (
    InstrumentClassificationCut,
    RetainedClassificationCut,
)
from portfolio_common.domain.reference_data.classification_history import (
    ClassificationHistoryConflict,
)
from portfolio_common.reference_classification_schema import InstrumentClassificationCutRecord
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


class ClassificationHistoryWriter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, source: InstrumentClassificationCut) -> RetainedClassificationCut:
        scope = (source.producer_id, source.classification_set_id, source.source_record_id)
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": json.dumps(["instrument-classification", *scope])},
        )
        model = InstrumentClassificationCutRecord
        statement = select(model).where(
            model.producer_id == source.producer_id,
            model.classification_set_id == source.classification_set_id,
            model.source_record_id == source.source_record_id,
        )
        existing = (
            await self._session.execute(
                statement.where(model.source_version == source.source_version)
            )
        ).scalar_one_or_none()
        cut_id, content_hash = source.identity()
        if existing is not None:
            if existing.cut_id != cut_id or existing.content_hash != content_hash:
                raise ClassificationHistoryConflict("CLASSIFICATION_SOURCE_VERSION_CONFLICT")
            return RetainedClassificationCut(
                cut_id=existing.cut_id,
                content_hash=existing.content_hash,
                received_at=existing.received_at,
                source=existing.payload,
            )
        latest = (
            await self._session.execute(statement.order_by(model.source_version.desc()).limit(1))
        ).scalar_one_or_none()
        if source.source_version != (
            1 if latest is None else latest.source_version + 1
        ) or source.predecessor_cut_id != (None if latest is None else latest.cut_id):
            raise ClassificationHistoryConflict("CLASSIFICATION_PREDECESSOR_CONFLICT")
        received_at = datetime.now(UTC)
        if source.generated_at > received_at:
            raise ClassificationHistoryConflict("CLASSIFICATION_SOURCE_GENERATED_IN_FUTURE")
        retained = RetainedClassificationCut(
            cut_id=cut_id,
            content_hash=content_hash,
            received_at=received_at,
            source=source,
        )
        self._session.add(
            model(
                cut_id=cut_id,
                content_hash=content_hash,
                producer_id=source.producer_id,
                classification_set_id=source.classification_set_id,
                source_record_id=source.source_record_id,
                source_version=source.source_version,
                predecessor_cut_id=source.predecessor_cut_id,
                payload=source.model_dump(mode="json"),
                received_at=retained.received_at,
            )
        )
        await self._session.flush()
        return retained
