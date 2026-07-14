"""Framework-neutral port for accrued-income purchase offsets."""

from typing import Protocol

from ...domain.cost_basis import CostBasisTransaction


class AccruedIncomeOffsetStatePort(Protocol):
    """Persist the remaining accrued-income offset established by a purchase."""

    async def upsert_accrued_income_offset(
        self,
        transaction: CostBasisTransaction,
    ) -> None: ...
