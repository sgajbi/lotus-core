from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.sell_state_dto import (
    SellCashLinkageResponse,
    SellDisposalRecord,
    SellDisposalsResponse,
)
from ..repositories.sell_state_repository import SellStateRepository


class SellStateService:
    def __init__(self, db: AsyncSession):
        self.repo = SellStateRepository(db)

    @staticmethod
    def _absolute_decimal(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return abs(value)

    @staticmethod
    def _net_proceeds(realized: Decimal | None, net_cost: Decimal | None) -> Decimal | None:
        if realized is None or net_cost is None:
            return None
        # net_cost is persisted as negative disposed basis for SELL; invert to recover proceeds.
        return realized - net_cost

    async def get_sell_disposals(
        self, portfolio_id: str, security_id: str
    ) -> SellDisposalsResponse:
        if not await self.repo.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")

        rows = await self.repo.get_sell_disposals(
            portfolio_id=portfolio_id, security_id=security_id
        )
        if not rows:
            raise LookupError(
                f"SELL state not found for portfolio {portfolio_id} and security {security_id}"
            )

        records = [
            SellDisposalRecord(
                transaction_id=txn.transaction_id,
                transaction_date=txn.transaction_date,
                instrument_id=txn.instrument_id,
                security_id=txn.security_id,
                quantity_disposed=self._absolute_decimal(txn.quantity) or Decimal("0"),
                disposal_cost_basis_base=self._absolute_decimal(txn.net_cost),
                disposal_cost_basis_local=self._absolute_decimal(txn.net_cost_local),
                net_sell_proceeds_base=self._net_proceeds(txn.realized_gain_loss, txn.net_cost),
                net_sell_proceeds_local=self._net_proceeds(
                    txn.realized_gain_loss_local, txn.net_cost_local
                ),
                realized_gain_loss_base=txn.realized_gain_loss,
                realized_gain_loss_local=txn.realized_gain_loss_local,
                economic_event_id=txn.economic_event_id,
                linked_transaction_group_id=txn.linked_transaction_group_id,
                calculation_policy_id=txn.calculation_policy_id,
                calculation_policy_version=txn.calculation_policy_version,
                source_system=txn.source_system,
            )
            for txn in rows
        ]

        return SellDisposalsResponse(
            portfolio_id=portfolio_id,
            security_id=security_id,
            sell_disposals=records,
        )

    async def get_sell_cash_linkage(
        self, portfolio_id: str, transaction_id: str
    ) -> SellCashLinkageResponse:
        if not await self.repo.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")

        row = await self.repo.get_sell_cash_linkage(
            portfolio_id=portfolio_id, transaction_id=transaction_id
        )
        if row is None:
            raise LookupError(
                f"SELL cash linkage not found for portfolio {portfolio_id} and transaction "
                f"{transaction_id}"
            )

        txn, cashflow = row
        return SellCashLinkageResponse(
            portfolio_id=portfolio_id,
            transaction_id=txn.transaction_id,
            transaction_type=txn.transaction_type,
            economic_event_id=txn.economic_event_id,
            linked_transaction_group_id=txn.linked_transaction_group_id,
            calculation_policy_id=txn.calculation_policy_id,
            calculation_policy_version=txn.calculation_policy_version,
            cashflow_date=cashflow.cashflow_date if cashflow else None,
            cashflow_amount=cashflow.amount if cashflow else None,
            cashflow_currency=cashflow.currency if cashflow else None,
            cashflow_classification=cashflow.classification if cashflow else None,
        )
