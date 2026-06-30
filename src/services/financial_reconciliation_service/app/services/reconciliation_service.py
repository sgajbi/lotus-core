from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import FinancialReconciliationFinding
from portfolio_common.decimal_amounts import decimal_or_none, required_decimal
from portfolio_common.fx_rates import coerce_positive_fx_rate_or_none
from portfolio_common.market_prices import coerce_positive_market_price_or_none
from portfolio_common.monitoring import observe_financial_reconciliation_run
from portfolio_common.valuation_prices import resolve_valuation_unit_price

from ..dtos import ReconciliationRunRequest
from ..repositories import ReconciliationRepository
from .runtime_providers import (
    IdGenerator,
    MonotonicTimer,
    SystemMonotonicTimer,
    UuidHexIdGenerator,
)

DEFAULT_VALUE_TOLERANCE = Decimal("0.0001")
ZERO = Decimal("0")
AUTHORITATIVE_PORTFOLIO_METRIC_NAMES = (
    "bod_market_value",
    "bod_cashflow",
    "eod_cashflow",
    "eod_market_value",
    "fees",
)


def _decimal_or_zero(value: object) -> Decimal:
    amount = decimal_or_none(value)
    return amount if amount is not None else ZERO


def _empty_authoritative_portfolio_metrics() -> dict[str, Decimal]:
    return {metric_name: ZERO for metric_name in AUTHORITATIVE_PORTFOLIO_METRIC_NAMES}


def _authoritative_metric_currencies(instrument: object, portfolio: object) -> tuple[str, str]:
    from_currency = (getattr(instrument, "currency", None) or "").strip()
    to_currency = (getattr(portfolio, "base_currency", None) or "").strip()
    return from_currency, to_currency


def _requires_authoritative_fx_rate(from_currency: str, to_currency: str) -> bool:
    return bool(from_currency and to_currency and from_currency != to_currency)


def _add_authoritative_position_metrics(
    metrics: dict[str, Decimal],
    *,
    position_row: object,
    rate: Decimal,
) -> None:
    metrics["bod_market_value"] += (
        _decimal_or_zero(getattr(position_row, "bod_market_value")) * rate
    )
    metrics["bod_cashflow"] += (
        _decimal_or_zero(getattr(position_row, "bod_cashflow_portfolio")) * rate
    )
    metrics["eod_cashflow"] += (
        _decimal_or_zero(getattr(position_row, "eod_cashflow_portfolio")) * rate
    )
    metrics["eod_market_value"] += (
        _decimal_or_zero(getattr(position_row, "eod_market_value")) * rate
    )
    metrics["fees"] += _decimal_or_zero(getattr(position_row, "fees")) * rate


def _cashflow_rule_mismatches(
    *,
    rule: Any,
    cashflow: Any,
) -> dict[str, tuple[object, object]]:
    comparisons = {
        "classification": (rule.classification, cashflow.classification),
        "timing": (rule.timing, cashflow.timing),
        "is_position_flow": (
            bool(rule.is_position_flow),
            bool(cashflow.is_position_flow),
        ),
        "is_portfolio_flow": (
            bool(rule.is_portfolio_flow),
            bool(cashflow.is_portfolio_flow),
        ),
    }
    return {
        field_name: (expected, observed)
        for field_name, (expected, observed) in comparisons.items()
        if expected != observed
    }


def _timeseries_scope_maps(
    *,
    portfolio_rows: list[Any],
    aggregate_rows: list[Any],
    snapshot_counts: list[Any],
) -> tuple[dict[ScopeKey, Any], dict[ScopeKey, Any], dict[ScopeKey, int]]:
    portfolio_by_key = {
        ScopeKey(row.portfolio_id, row.date, row.epoch): row for row in portfolio_rows
    }
    aggregate_by_key = {
        ScopeKey(row.portfolio_id, row.date, row.epoch): row for row in aggregate_rows
    }
    snapshot_count_by_key = {
        ScopeKey(row.portfolio_id, row.date, row.epoch): int(row.snapshot_count)
        for row in snapshot_counts
    }
    return portfolio_by_key, aggregate_by_key, snapshot_count_by_key


def _timeseries_integrity_scope_keys(
    *,
    portfolio_by_key: dict[ScopeKey, Any],
    aggregate_by_key: dict[ScopeKey, Any],
    snapshot_count_by_key: dict[ScopeKey, int],
) -> list[ScopeKey]:
    if portfolio_by_key:
        all_keys = set(portfolio_by_key)
    else:
        all_keys = set(aggregate_by_key) | set(snapshot_count_by_key)
    return sorted(all_keys, key=lambda item: (item.portfolio_id, item.business_date, item.epoch))


def _portfolio_timeseries_metric_pairs(
    *,
    portfolio_row: Any,
    authoritative_metrics: dict[str, Decimal],
) -> dict[str, tuple[Decimal, Decimal]]:
    return {
        "bod_market_value": (
            required_decimal(
                portfolio_row.bod_market_value,
                field_name="portfolio_timeseries.bod_market_value",
            ),
            authoritative_metrics["bod_market_value"],
        ),
        "bod_cashflow": (
            required_decimal(
                portfolio_row.bod_cashflow,
                field_name="portfolio_timeseries.bod_cashflow",
            ),
            authoritative_metrics["bod_cashflow"],
        ),
        "eod_cashflow": (
            required_decimal(
                portfolio_row.eod_cashflow,
                field_name="portfolio_timeseries.eod_cashflow",
            ),
            authoritative_metrics["eod_cashflow"],
        ),
        "eod_market_value": (
            required_decimal(
                portfolio_row.eod_market_value,
                field_name="portfolio_timeseries.eod_market_value",
            ),
            authoritative_metrics["eod_market_value"],
        ),
        "fees": (
            required_decimal(
                portfolio_row.fees,
                field_name="portfolio_timeseries.fees",
            ),
            authoritative_metrics["fees"],
        ),
    }


def _timeseries_metric_mismatches(
    *,
    portfolio_row: Any,
    authoritative_metrics: dict[str, Decimal],
    tolerance: Decimal,
) -> dict[str, dict[str, str]]:
    mismatches = {}
    metric_pairs = _portfolio_timeseries_metric_pairs(
        portfolio_row=portfolio_row,
        authoritative_metrics=authoritative_metrics,
    )
    for metric_name, (portfolio_value, aggregate_value) in metric_pairs.items():
        delta = portfolio_value - aggregate_value
        if abs(delta) > tolerance:
            mismatches[metric_name] = {
                "portfolio_timeseries": str(portfolio_value),
                "position_aggregate": str(aggregate_value),
                "delta": str(delta),
            }
    return mismatches


@dataclass(frozen=True, slots=True)
class ScopeKey:
    portfolio_id: str
    business_date: date
    epoch: int


@dataclass(frozen=True, slots=True)
class AutomaticBundleOutcome:
    outcome_status: str
    blocking_reconciliation_types: list[str]
    run_ids: dict[str, str]
    error_count: int
    warning_count: int


class ReconciliationService:
    def __init__(
        self,
        repository: ReconciliationRepository,
        *,
        monotonic_timer: MonotonicTimer | None = None,
        id_generator: IdGenerator | None = None,
    ):
        self.repository = repository
        self._monotonic_timer = monotonic_timer or SystemMonotonicTimer()
        self._id_generator = id_generator or UuidHexIdGenerator()

    async def _aggregate_authoritative_portfolio_metrics(
        self,
        *,
        portfolio_id: str,
        business_date: date,
        epoch: int,
    ) -> tuple[dict[str, Decimal], int]:
        authoritative_rows = await self.repository.fetch_authoritative_position_timeseries_rows(
            portfolio_id=portfolio_id,
            business_date=business_date,
            epoch=epoch,
        )
        metrics = _empty_authoritative_portfolio_metrics()
        fx_cache: dict[tuple[str, str, date], Decimal] = {}

        for position_row, instrument, portfolio in authoritative_rows:
            rate = await self._authoritative_portfolio_fx_rate(
                position_row=position_row,
                instrument=instrument,
                portfolio=portfolio,
                fx_cache=fx_cache,
            )
            if rate == ZERO:
                continue
            _add_authoritative_position_metrics(metrics, position_row=position_row, rate=rate)

        return metrics, len(authoritative_rows)

    async def _authoritative_portfolio_fx_rate(
        self,
        *,
        position_row: object,
        instrument: object,
        portfolio: object,
        fx_cache: dict[tuple[str, str, date], Decimal],
    ) -> Decimal:
        from_currency, to_currency = _authoritative_metric_currencies(instrument, portfolio)
        if not _requires_authoritative_fx_rate(from_currency, to_currency):
            return Decimal("1")

        position_date = getattr(position_row, "date")
        cache_key = (from_currency, to_currency, position_date)
        if cache_key not in fx_cache:
            fx_rate = await self.repository.fetch_latest_fx_rate(
                from_currency=from_currency,
                to_currency=to_currency,
                business_date=position_date,
            )
            fx_cache[cache_key] = (
                coerce_positive_fx_rate_or_none(fx_rate.rate) if fx_rate else None
            ) or ZERO
        return fx_cache[cache_key]

    @staticmethod
    def _expected_market_value_local(
        *,
        quantity: Decimal,
        market_price: Decimal,
        cost_basis_local: Decimal,
        product_type: str | None,
    ) -> Decimal:
        valuation_price_local = resolve_valuation_unit_price(
            market_price=market_price,
            quantity=quantity,
            cost_basis_local=cost_basis_local,
            product_type=product_type,
        )
        return quantity * valuation_price_local

    @staticmethod
    def _automatic_dedupe_key(
        *,
        reconciliation_type: str,
        request: ReconciliationRunRequest,
    ) -> str | None:
        if request.requested_by != "system_pipeline":
            return None
        if request.portfolio_id is None or request.business_date is None:
            return None
        epoch = request.epoch if request.epoch is not None else 0
        return (
            f"auto:{reconciliation_type}:{request.portfolio_id}:"
            f"{request.business_date.isoformat()}:{epoch}"
        )

    @staticmethod
    def determine_automatic_bundle_outcome(
        runs: dict[str, object],
    ) -> AutomaticBundleOutcome:
        blocking_types: list[str] = []
        run_ids: dict[str, str] = {}
        error_count = 0
        warning_count = 0
        has_failed_run = False

        for reconciliation_type, run in runs.items():
            run_ids[reconciliation_type] = getattr(run, "run_id")
            status = getattr(run, "status", None)
            summary = getattr(run, "summary", None) or {}
            run_error_count = int(summary.get("error_count", 0) or 0)
            run_warning_count = int(summary.get("warning_count", 0) or 0)
            error_count += run_error_count
            warning_count += run_warning_count

            if status == "FAILED":
                has_failed_run = True
                blocking_types.append(reconciliation_type)
                continue
            if run_error_count > 0:
                blocking_types.append(reconciliation_type)

        if has_failed_run:
            outcome_status = "FAILED"
        elif blocking_types:
            outcome_status = "REQUIRES_REPLAY"
        else:
            outcome_status = "COMPLETED"

        return AutomaticBundleOutcome(
            outcome_status=outcome_status,
            blocking_reconciliation_types=sorted(set(blocking_types)),
            run_ids=run_ids,
            error_count=error_count,
            warning_count=warning_count,
        )

    async def run_transaction_cashflow(
        self,
        *,
        request: ReconciliationRunRequest,
        correlation_id: str | None,
    ):
        started_at = self._monotonic_timer.seconds()
        dedupe_key = self._automatic_dedupe_key(
            reconciliation_type="transaction_cashflow",
            request=request,
        )
        run, created = await self.repository.create_run(
            reconciliation_type="transaction_cashflow",
            portfolio_id=request.portfolio_id,
            business_date=request.business_date,
            epoch=request.epoch,
            requested_by=request.requested_by,
            dedupe_key=dedupe_key,
            correlation_id=correlation_id,
            tolerance=request.tolerance,
        )
        if not created:
            return run
        rows = await self.repository.fetch_transaction_cashflow_rows(
            portfolio_id=request.portfolio_id,
            business_date=request.business_date,
        )
        findings = self._transaction_cashflow_findings(
            run_id=run.run_id,
            request_epoch=request.epoch,
            rows=rows,
        )
        examined = len(rows)

        await self.repository.add_findings(findings)
        summary = self._summary(examined=examined, findings=findings)
        await self.repository.mark_run_completed(run, status="COMPLETED", summary=summary)
        observe_financial_reconciliation_run(
            "transaction_cashflow",
            "COMPLETED",
            self._monotonic_timer.seconds() - started_at,
            findings,
        )
        return run

    def _transaction_cashflow_findings(
        self,
        *,
        run_id: str,
        request_epoch: int | None,
        rows: list[tuple[Any, Any, Any | None]],
    ) -> list[FinancialReconciliationFinding]:
        findings: list[FinancialReconciliationFinding] = []
        for transaction, rule, cashflow in rows:
            finding = self._transaction_cashflow_finding(
                run_id=run_id,
                request_epoch=request_epoch,
                transaction=transaction,
                rule=rule,
                cashflow=cashflow,
            )
            if finding is not None:
                findings.append(finding)
        return findings

    def _transaction_cashflow_finding(
        self,
        *,
        run_id: str,
        request_epoch: int | None,
        transaction: Any,
        rule: Any,
        cashflow: Any | None,
    ) -> FinancialReconciliationFinding | None:
        if cashflow is None:
            return self._missing_cashflow_finding(
                run_id=run_id,
                request_epoch=request_epoch,
                transaction=transaction,
                rule=rule,
            )

        mismatches = _cashflow_rule_mismatches(rule=rule, cashflow=cashflow)
        if not mismatches:
            return None
        return self._cashflow_rule_mismatch_finding(
            run_id=run_id,
            transaction=transaction,
            cashflow=cashflow,
            mismatches=mismatches,
        )

    def _missing_cashflow_finding(
        self,
        *,
        run_id: str,
        request_epoch: int | None,
        transaction: Any,
        rule: Any,
    ) -> FinancialReconciliationFinding:
        return self._build_finding(
            run_id=run_id,
            reconciliation_type="transaction_cashflow",
            finding_type="missing_cashflow",
            severity="ERROR",
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            transaction_id=transaction.transaction_id,
            business_date=transaction.transaction_date.date(),
            epoch=request_epoch,
            expected_value={
                "classification": rule.classification,
                "timing": rule.timing,
                "is_position_flow": rule.is_position_flow,
                "is_portfolio_flow": rule.is_portfolio_flow,
            },
            observed_value=None,
            detail={
                "transaction_type": transaction.transaction_type,
                "cash_entry_mode": transaction.cash_entry_mode,
            },
        )

    def _cashflow_rule_mismatch_finding(
        self,
        *,
        run_id: str,
        transaction: Any,
        cashflow: Any,
        mismatches: dict[str, tuple[object, object]],
    ) -> FinancialReconciliationFinding:
        return self._build_finding(
            run_id=run_id,
            reconciliation_type="transaction_cashflow",
            finding_type="cashflow_rule_mismatch",
            severity="ERROR",
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            transaction_id=transaction.transaction_id,
            business_date=cashflow.cashflow_date,
            epoch=cashflow.epoch,
            expected_value={key: expected for key, (expected, _) in mismatches.items()},
            observed_value={key: observed for key, (_, observed) in mismatches.items()},
            detail={"transaction_type": transaction.transaction_type},
        )

    async def run_position_valuation(
        self,
        *,
        request: ReconciliationRunRequest,
        correlation_id: str | None,
    ):
        started_at = self._monotonic_timer.seconds()
        tolerance = request.tolerance or DEFAULT_VALUE_TOLERANCE
        dedupe_key = self._automatic_dedupe_key(
            reconciliation_type="position_valuation",
            request=request,
        )
        run, created = await self.repository.create_run(
            reconciliation_type="position_valuation",
            portfolio_id=request.portfolio_id,
            business_date=request.business_date,
            epoch=request.epoch,
            requested_by=request.requested_by,
            dedupe_key=dedupe_key,
            correlation_id=correlation_id,
            tolerance=tolerance,
        )
        if not created:
            return run
        rows = await self.repository.fetch_position_valuation_rows(
            portfolio_id=request.portfolio_id,
            business_date=request.business_date,
            epoch=request.epoch,
        )
        findings: list[FinancialReconciliationFinding] = []
        examined = 0
        for snapshot, instrument, _portfolio in rows:
            examined += 1
            quantity = required_decimal(snapshot.quantity, field_name="snapshot.quantity")
            cost_basis_local = required_decimal(
                snapshot.cost_basis_local,
                field_name="snapshot.cost_basis_local",
            )
            market_price = coerce_positive_market_price_or_none(snapshot.market_price)
            if market_price is None:
                findings.append(
                    self._build_finding(
                        run_id=run.run_id,
                        reconciliation_type="position_valuation",
                        finding_type="invalid_market_price",
                        severity="ERROR",
                        portfolio_id=snapshot.portfolio_id,
                        security_id=snapshot.security_id,
                        transaction_id=None,
                        business_date=snapshot.date,
                        epoch=snapshot.epoch,
                        expected_value={"market_price": ">0"},
                        observed_value={"market_price": str(snapshot.market_price)},
                        detail={
                            "quantity": str(snapshot.quantity),
                            "product_type": instrument.product_type,
                        },
                    )
                )
                continue
            expected_market_value_local = self._expected_market_value_local(
                quantity=quantity,
                market_price=market_price,
                cost_basis_local=cost_basis_local,
                product_type=instrument.product_type,
            )
            expected_unrealized = expected_market_value_local - cost_basis_local
            observed_market_value_local = required_decimal(
                snapshot.market_value_local,
                field_name="snapshot.market_value_local",
            )
            market_delta = observed_market_value_local - expected_market_value_local
            if abs(market_delta) > tolerance:
                findings.append(
                    self._build_finding(
                        run_id=run.run_id,
                        reconciliation_type="position_valuation",
                        finding_type="market_value_local_mismatch",
                        severity="ERROR",
                        portfolio_id=snapshot.portfolio_id,
                        security_id=snapshot.security_id,
                        transaction_id=None,
                        business_date=snapshot.date,
                        epoch=snapshot.epoch,
                        expected_value={"market_value_local": str(expected_market_value_local)},
                        observed_value={
                            "market_value_local": str(observed_market_value_local),
                            "delta": str(market_delta),
                        },
                        detail={
                            "quantity": str(snapshot.quantity),
                            "market_price": str(snapshot.market_price),
                            "product_type": instrument.product_type,
                        },
                    )
                )

            observed_unrealized = required_decimal(
                snapshot.unrealized_gain_loss_local,
                field_name="snapshot.unrealized_gain_loss_local",
            )
            unrealized_delta = observed_unrealized - expected_unrealized
            if abs(unrealized_delta) > tolerance:
                findings.append(
                    self._build_finding(
                        run_id=run.run_id,
                        reconciliation_type="position_valuation",
                        finding_type="unrealized_gain_loss_local_mismatch",
                        severity="ERROR",
                        portfolio_id=snapshot.portfolio_id,
                        security_id=snapshot.security_id,
                        transaction_id=None,
                        business_date=snapshot.date,
                        epoch=snapshot.epoch,
                        expected_value={"unrealized_gain_loss_local": str(expected_unrealized)},
                        observed_value={
                            "unrealized_gain_loss_local": str(observed_unrealized),
                            "delta": str(unrealized_delta),
                        },
                        detail={
                            "market_value_local": str(observed_market_value_local),
                            "cost_basis_local": str(snapshot.cost_basis_local),
                            "product_type": instrument.product_type,
                        },
                    )
                )

        await self.repository.add_findings(findings)
        summary = self._summary(examined=examined, findings=findings)
        await self.repository.mark_run_completed(run, status="COMPLETED", summary=summary)
        observe_financial_reconciliation_run(
            "position_valuation",
            "COMPLETED",
            self._monotonic_timer.seconds() - started_at,
            findings,
        )
        return run

    async def run_timeseries_integrity(
        self,
        *,
        request: ReconciliationRunRequest,
        correlation_id: str | None,
    ):
        started_at = self._monotonic_timer.seconds()
        tolerance = request.tolerance or DEFAULT_VALUE_TOLERANCE
        dedupe_key = self._automatic_dedupe_key(
            reconciliation_type="timeseries_integrity",
            request=request,
        )
        run, created = await self.repository.create_run(
            reconciliation_type="timeseries_integrity",
            portfolio_id=request.portfolio_id,
            business_date=request.business_date,
            epoch=request.epoch,
            requested_by=request.requested_by,
            dedupe_key=dedupe_key,
            correlation_id=correlation_id,
            tolerance=tolerance,
        )
        if not created:
            return run
        portfolio_rows = await self.repository.fetch_portfolio_timeseries_rows(
            portfolio_id=request.portfolio_id,
            business_date=request.business_date,
            epoch=request.epoch,
        )
        aggregate_rows = await self.repository.fetch_position_timeseries_aggregates(
            portfolio_id=request.portfolio_id,
            business_date=request.business_date,
            epoch=request.epoch,
        )
        snapshot_counts = await self.repository.fetch_snapshot_counts(
            portfolio_id=request.portfolio_id,
            business_date=request.business_date,
            epoch=request.epoch,
        )
        findings, examined = await self._timeseries_integrity_findings(
            run_id=run.run_id,
            portfolio_rows=portfolio_rows,
            aggregate_rows=aggregate_rows,
            snapshot_counts=snapshot_counts,
            tolerance=tolerance,
        )

        await self.repository.add_findings(findings)
        summary = self._summary(examined=examined, findings=findings)
        await self.repository.mark_run_completed(run, status="COMPLETED", summary=summary)
        observe_financial_reconciliation_run(
            "timeseries_integrity",
            "COMPLETED",
            self._monotonic_timer.seconds() - started_at,
            findings,
        )
        return run

    async def _timeseries_integrity_findings(
        self,
        *,
        run_id: str,
        portfolio_rows: list[Any],
        aggregate_rows: list[Any],
        snapshot_counts: list[Any],
        tolerance: Decimal,
    ) -> tuple[list[FinancialReconciliationFinding], int]:
        portfolio_by_key, aggregate_by_key, snapshot_count_by_key = _timeseries_scope_maps(
            portfolio_rows=portfolio_rows,
            aggregate_rows=aggregate_rows,
            snapshot_counts=snapshot_counts,
        )
        findings: list[FinancialReconciliationFinding] = []
        scope_keys = _timeseries_integrity_scope_keys(
            portfolio_by_key=portfolio_by_key,
            aggregate_by_key=aggregate_by_key,
            snapshot_count_by_key=snapshot_count_by_key,
        )
        for key in scope_keys:
            findings.extend(
                await self._timeseries_integrity_findings_for_key(
                    run_id=run_id,
                    key=key,
                    portfolio_by_key=portfolio_by_key,
                    aggregate_by_key=aggregate_by_key,
                    snapshot_count_by_key=snapshot_count_by_key,
                    tolerance=tolerance,
                )
            )
        return findings, len(scope_keys)

    async def _timeseries_integrity_findings_for_key(
        self,
        *,
        run_id: str,
        key: ScopeKey,
        portfolio_by_key: dict[ScopeKey, Any],
        aggregate_by_key: dict[ScopeKey, Any],
        snapshot_count_by_key: dict[ScopeKey, int],
        tolerance: Decimal,
    ) -> list[FinancialReconciliationFinding]:
        portfolio_row = portfolio_by_key.get(key)
        if portfolio_row is None:
            aggregate_row = aggregate_by_key.get(key)
            return (
                []
                if aggregate_row is None
                else [self._missing_portfolio_timeseries_finding(run_id, key, aggregate_row)]
            )

        (
            authoritative_metrics,
            authoritative_position_count,
        ) = await self._aggregate_authoritative_portfolio_metrics(
            portfolio_id=key.portfolio_id,
            business_date=key.business_date,
            epoch=key.epoch,
        )
        authoritative_snapshot_count = await self.repository.fetch_authoritative_snapshot_count(
            portfolio_id=key.portfolio_id,
            business_date=key.business_date,
            epoch=key.epoch,
        )
        if authoritative_position_count == 0:
            return [self._missing_position_timeseries_finding(run_id, key)]

        findings = self._timeseries_completeness_findings(
            run_id=run_id,
            key=key,
            authoritative_position_count=authoritative_position_count,
            authoritative_snapshot_count=authoritative_snapshot_count,
        )
        mismatch = self._portfolio_timeseries_aggregate_mismatch_finding(
            run_id=run_id,
            key=key,
            portfolio_row=portfolio_row,
            authoritative_metrics=authoritative_metrics,
            tolerance=tolerance,
        )
        if mismatch is not None:
            findings.append(mismatch)
        return findings

    def _missing_portfolio_timeseries_finding(
        self, run_id: str, key: ScopeKey, aggregate_row: Any
    ) -> FinancialReconciliationFinding:
        return self._build_finding(
            run_id=run_id,
            reconciliation_type="timeseries_integrity",
            finding_type="missing_portfolio_timeseries",
            severity="ERROR",
            portfolio_id=key.portfolio_id,
            security_id=None,
            transaction_id=None,
            business_date=key.business_date,
            epoch=key.epoch,
            expected_value={"portfolio_timeseries": "present"},
            observed_value={"portfolio_timeseries": "missing"},
            detail={"position_timeseries_rows": int(aggregate_row.position_row_count)},
        )

    def _missing_position_timeseries_finding(
        self, run_id: str, key: ScopeKey
    ) -> FinancialReconciliationFinding:
        return self._build_finding(
            run_id=run_id,
            reconciliation_type="timeseries_integrity",
            finding_type="missing_position_timeseries",
            severity="ERROR",
            portfolio_id=key.portfolio_id,
            security_id=None,
            transaction_id=None,
            business_date=key.business_date,
            epoch=key.epoch,
            expected_value={"position_timeseries_rows": ">=1"},
            observed_value={"position_timeseries_rows": 0},
            detail=None,
        )

    def _timeseries_completeness_findings(
        self,
        *,
        run_id: str,
        key: ScopeKey,
        authoritative_position_count: int,
        authoritative_snapshot_count: int,
    ) -> list[FinancialReconciliationFinding]:
        if authoritative_position_count == authoritative_snapshot_count:
            return []
        return [
            self._build_finding(
                run_id=run_id,
                reconciliation_type="timeseries_integrity",
                finding_type="position_timeseries_completeness_gap",
                severity="ERROR",
                portfolio_id=key.portfolio_id,
                security_id=None,
                transaction_id=None,
                business_date=key.business_date,
                epoch=key.epoch,
                expected_value={"snapshot_count": authoritative_snapshot_count},
                observed_value={"position_timeseries_count": authoritative_position_count},
                detail=None,
            )
        ]

    def _portfolio_timeseries_aggregate_mismatch_finding(
        self,
        *,
        run_id: str,
        key: ScopeKey,
        portfolio_row: Any,
        authoritative_metrics: dict[str, Decimal],
        tolerance: Decimal,
    ) -> FinancialReconciliationFinding | None:
        mismatches = _timeseries_metric_mismatches(
            portfolio_row=portfolio_row,
            authoritative_metrics=authoritative_metrics,
            tolerance=tolerance,
        )
        if not mismatches:
            return None
        return self._build_finding(
            run_id=run_id,
            reconciliation_type="timeseries_integrity",
            finding_type="portfolio_timeseries_aggregate_mismatch",
            severity="ERROR",
            portfolio_id=key.portfolio_id,
            security_id=None,
            transaction_id=None,
            business_date=key.business_date,
            epoch=key.epoch,
            expected_value={k: v["position_aggregate"] for k, v in mismatches.items()},
            observed_value={k: v["portfolio_timeseries"] for k, v in mismatches.items()},
            detail=mismatches,
        )

    async def run_automatic_bundle(
        self,
        *,
        request: ReconciliationRunRequest,
        correlation_id: str | None,
        reconciliation_types: list[str],
    ) -> dict[str, object]:
        results: dict[str, object] = {}
        for reconciliation_type in reconciliation_types:
            if reconciliation_type == "transaction_cashflow":
                results[reconciliation_type] = await self.run_transaction_cashflow(
                    request=request,
                    correlation_id=correlation_id,
                )
                continue
            if reconciliation_type == "position_valuation":
                results[reconciliation_type] = await self.run_position_valuation(
                    request=request,
                    correlation_id=correlation_id,
                )
                continue
            if reconciliation_type == "timeseries_integrity":
                results[reconciliation_type] = await self.run_timeseries_integrity(
                    request=request,
                    correlation_id=correlation_id,
                )
                continue
            raise ValueError(f"Unsupported reconciliation type '{reconciliation_type}'.")
        return results

    def _summary(self, *, examined: int, findings: list[FinancialReconciliationFinding]) -> dict:
        error_count = sum(1 for finding in findings if finding.severity == "ERROR")
        warning_count = sum(1 for finding in findings if finding.severity == "WARNING")
        return {
            "examined_count": examined,
            "finding_count": len(findings),
            "error_count": error_count,
            "warning_count": warning_count,
            "passed": error_count == 0,
        }

    def _build_finding(
        self,
        *,
        run_id: str,
        reconciliation_type: str,
        finding_type: str,
        severity: str,
        portfolio_id: str | None,
        security_id: str | None,
        transaction_id: str | None,
        business_date: date | None,
        epoch: int | None,
        expected_value: dict | None,
        observed_value: dict | None,
        detail: dict | None,
    ) -> FinancialReconciliationFinding:
        return FinancialReconciliationFinding(
            finding_id=f"finding-{self._id_generator.hex()}",
            run_id=run_id,
            reconciliation_type=reconciliation_type,
            finding_type=finding_type,
            severity=severity,
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_id=transaction_id,
            business_date=business_date,
            epoch=epoch,
            expected_value=expected_value,
            observed_value=observed_value,
            detail=detail,
        )
