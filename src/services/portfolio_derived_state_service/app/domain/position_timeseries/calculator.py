"""Pure calculation policy for one position-timeseries business day."""

from dataclasses import dataclass, replace
from decimal import Decimal

from portfolio_common.domain.analytics.cashflow_semantics import (
    normalize_cashflow_timing,
    normalize_position_flow_amount,
)
from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.decimal_amount import decimal_or_none

from .models import PositionCashflowRecord, PositionSnapshotRecord, PositionTimeseriesRecord
from .numeric_policy import POSITION_TIMESERIES_LEDGER_OUTPUT_V1

ZERO = Decimal("0")


class PositionSnapshotNotValuedError(ValueError):
    """Raised when numeric timeseries input lacks an authoritative market value."""


def _decimal_or_zero(value: object) -> Decimal:
    amount = decimal_or_none(value)
    return amount if amount is not None else ZERO


def _beginning_market_value(previous_snapshot: PositionSnapshotRecord | None) -> Decimal:
    if previous_snapshot is None:
        return ZERO
    return _required_market_value(previous_snapshot, boundary="beginning")


def _required_market_value(
    snapshot: PositionSnapshotRecord,
    *,
    boundary: str,
) -> Decimal:
    if snapshot.market_value_local is None:
        raise PositionSnapshotNotValuedError(
            f"{boundary} position snapshot has no authoritative local market value"
        )
    return _decimal_or_zero(snapshot.market_value_local)


def _average_cost(*, cost_basis: Decimal, quantity: Decimal) -> Decimal:
    if not quantity:
        return ZERO
    return POSITION_TIMESERIES_LEDGER_OUTPUT_V1.divide(
        cost_basis,
        quantity,
        field_name="cost",
    )


def _is_expense_cashflow(cashflow: PositionCashflowRecord) -> bool:
    return str(cashflow.classification or "").strip().upper() == "EXPENSE"


@dataclass(slots=True)
class _CashflowBuckets:
    bod_position: Decimal = ZERO
    eod_position: Decimal = ZERO
    bod_portfolio: Decimal = ZERO
    eod_portfolio: Decimal = ZERO
    fees: Decimal = ZERO

    def add(self, cashflow: PositionCashflowRecord) -> None:
        cashflow_amount = _decimal_or_zero(cashflow.amount)
        timing = normalize_cashflow_timing(cashflow.timing)
        if cashflow.is_position_flow:
            self._add_position_flow(cashflow, cashflow_amount, timing)
        if cashflow.is_portfolio_flow:
            self._add_portfolio_flow(cashflow_amount, timing)
        if _is_expense_cashflow(cashflow):
            self.fees = POSITION_TIMESERIES_LEDGER_OUTPUT_V1.add(
                self.fees,
                abs(cashflow_amount),
                field_name="fees",
            )

    def _add_position_flow(
        self, cashflow: PositionCashflowRecord, amount: Decimal, timing: str
    ) -> None:
        normalized_position_amount = normalize_position_flow_amount(
            amount=amount,
            classification=str(cashflow.classification),
        )
        if timing == "BOD":
            self.bod_position = POSITION_TIMESERIES_LEDGER_OUTPUT_V1.add(
                self.bod_position,
                normalized_position_amount,
                field_name="bod_cashflow_position",
            )
        else:
            self.eod_position = POSITION_TIMESERIES_LEDGER_OUTPUT_V1.add(
                self.eod_position,
                normalized_position_amount,
                field_name="eod_cashflow_position",
            )

    def _add_portfolio_flow(self, amount: Decimal, timing: str) -> None:
        if timing == "BOD":
            self.bod_portfolio = POSITION_TIMESERIES_LEDGER_OUTPUT_V1.add(
                self.bod_portfolio,
                amount,
                field_name="bod_cashflow_portfolio",
            )
        else:
            self.eod_portfolio = POSITION_TIMESERIES_LEDGER_OUTPUT_V1.add(
                self.eod_portfolio,
                amount,
                field_name="eod_cashflow_portfolio",
            )


def _cashflow_buckets(cashflows: list[PositionCashflowRecord]) -> _CashflowBuckets:
    buckets = _CashflowBuckets()
    for cashflow in cashflows:
        buckets.add(cashflow)
    return buckets


def calculate_position_timeseries(
    *,
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord | None,
    cashflows: list[PositionCashflowRecord],
    epoch: int,
) -> PositionTimeseriesRecord:
    """Calculate one complete position-timeseries record."""

    eod_market_value = _required_market_value(current_snapshot, boundary="end-of-day")
    eod_quantity = _decimal_or_zero(current_snapshot.quantity)
    eod_cost_basis = _decimal_or_zero(current_snapshot.cost_basis_local)
    cashflow_buckets = _cashflow_buckets(cashflows)

    record = PositionTimeseriesRecord(
        portfolio_id=current_snapshot.portfolio_id,
        security_id=current_snapshot.security_id,
        date=current_snapshot.date,
        epoch=epoch,
        bod_market_value=_beginning_market_value(previous_snapshot),
        bod_cashflow_position=cashflow_buckets.bod_position,
        eod_cashflow_position=cashflow_buckets.eod_position,
        bod_cashflow_portfolio=cashflow_buckets.bod_portfolio,
        eod_cashflow_portfolio=cashflow_buckets.eod_portfolio,
        eod_market_value=eod_market_value,
        fees=cashflow_buckets.fees,
        quantity=eod_quantity,
        cost=_average_cost(cost_basis=eod_cost_basis, quantity=eod_quantity),
    )
    return replace(
        record,
        calculation_lineage=build_calculation_lineage(
            algorithm_id="position-timeseries-materialization",
            algorithm_version=1,
            intermediate_precision=POSITION_TIMESERIES_LEDGER_OUTPUT_V1.working_precision,
            input_payload=_position_timeseries_input(
                current_snapshot=current_snapshot,
                previous_snapshot=previous_snapshot,
                cashflows=cashflows,
                epoch=epoch,
            ),
            output_payload=_position_timeseries_output(record),
            numeric_output_policy=POSITION_TIMESERIES_LEDGER_OUTPUT_V1.lineage_identity(),
        ),
    )


def _position_timeseries_input(
    *,
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord | None,
    cashflows: list[PositionCashflowRecord],
    epoch: int,
) -> dict[str, object]:
    """Return the valuation and cashflow facts used for one position day."""

    def snapshot_payload(snapshot: PositionSnapshotRecord) -> dict[str, object]:
        return {
            "cost_basis_local": snapshot.cost_basis_local,
            "date": snapshot.date,
            "epoch": snapshot.epoch,
            "market_value_local": snapshot.market_value_local,
            "portfolio_id": snapshot.portfolio_id,
            "quantity": snapshot.quantity,
            "security_id": snapshot.security_id,
            "valuation_status": snapshot.valuation_status,
        }

    return {
        "cashflows": [
            {
                "amount": cashflow.amount,
                "cashflow_date": cashflow.cashflow_date,
                "classification": cashflow.classification,
                "epoch": cashflow.epoch,
                "is_portfolio_flow": cashflow.is_portfolio_flow,
                "is_position_flow": cashflow.is_position_flow,
                "timing": cashflow.timing,
                "transaction_id": cashflow.transaction_id,
            }
            for cashflow in cashflows
        ],
        "current_snapshot": snapshot_payload(current_snapshot),
        "epoch": epoch,
        "previous_snapshot": (
            snapshot_payload(previous_snapshot) if previous_snapshot is not None else None
        ),
    }


def _position_timeseries_output(record: PositionTimeseriesRecord) -> dict[str, object]:
    """Return every calculated field persisted for one position day."""

    return {
        "bod_cashflow_portfolio": record.bod_cashflow_portfolio,
        "bod_cashflow_position": record.bod_cashflow_position,
        "bod_market_value": record.bod_market_value,
        "cost": record.cost,
        "date": record.date,
        "eod_cashflow_portfolio": record.eod_cashflow_portfolio,
        "eod_cashflow_position": record.eod_cashflow_position,
        "eod_market_value": record.eod_market_value,
        "epoch": record.epoch,
        "fees": record.fees,
        "portfolio_id": record.portfolio_id,
        "quantity": record.quantity,
        "security_id": record.security_id,
    }
