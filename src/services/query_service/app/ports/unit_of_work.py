from __future__ import annotations

from typing import Any, Protocol


class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def refresh(self, entity: Any) -> None: ...
