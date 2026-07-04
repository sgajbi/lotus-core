from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from ..application.upload_commands import UploadEntity


class UploadRecordPublisher(Protocol):
    async def publish_records(
        self,
        entity_type: UploadEntity,
        valid_models: list[BaseModel],
    ) -> None: ...
