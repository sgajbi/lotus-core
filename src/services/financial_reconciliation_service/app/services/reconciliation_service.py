from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

from portfolio_common.database_models import FinancialReconciliationFinding
from portfolio_common.monitoring import observe_financial_reconciliation_run

from ..dtos import ReconciliationRunRequest
from ..repositories import ReconciliationRepository

DEFAULT_VALUE_TOLERANCE = Decimal("0.0001")
ZERO = Decimal("0")


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
    def __init__(self, repository: ReconciliationRepository):
        self.repository = repository

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
        metrics = {
            "bod_market_value": ZERO,
            "bod_cashflow": ZERO,
            "eod_cashflow": ZERO,
            "eod_market_value": ZERO,
            "fees": ZERO,
        }
        fx_cache: dict[tuple[str, str, date], Decimal] = {}

        for position_row, instrument, portfolio in authoritative_rows:
            from_currency = (instrument.currency or "").strip()
            to_currency = (portfolio.base_currency or "").strip()
            rate = Decimal("1")
            if from_currency and to_currency and from_currency != to_currency:
                cache_key = (from_currency, to_currency, position_row.date)
                if cache_key not in fx_cache:
                    fx_rate = await self.repository.fetch_latest_fx_rate(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        business_date=position_row.date,
                    )
                    fx_cache[cache_key] = Decimal(str(fx_rate.rate)) if fx_rate else ZERO
                rate = fx_cache[cache_key]
                if rate == ZERO:
                    continue

            metrics["bod_market_value"] += Decimal(str(position_row.bod_market_value or ZERO)) * rate
            metrics["bod_cashflow"] += Decimal(
                str(position_row.bod_cashflow_portfolio or ZERO)
            ) * rate
            metrics["eod_cashflow"] += Decimal(
                str(position_row.eod_cashflow_portfolio or ZERO)
            ) * rate
            metrics["eod_market_value"] += Decimal(str(position_row.eod_market_value or ZERO)) * rate
            metrics["fees"] += Decimal(str(position_row.fees or ZERO)) * rate

        return metrics, len(authoritative_rows)

    @staticmethod
    def _expected_market_value_local(
        *,
        quantity: Decimal,
        market_price: Decimal,
        cost_basis_local: Decimal,
        product_type: str | None,
    ) -> Decimal:
        normalized_product_type = (product_type or "").strip().upper()
        valuation_price_local = market_price
        if normalized_product_type == "BOND" and not quantity.is_zero():
            average_cost_local = abs(cost_basis_local / quantity)
            absolute_price_local = abs(valuation_price_local)
            if (
                absolute_price_local > Decimal("0")
                and absolute_price_local < Decimal("200")
                and average_cost_local >= Decimal("500")
            ):
                price_ratio = average_cost_local / absolute_price_local
                if price_ratio >= Decimal("50"):
                    valuation_price_local *= Decimal("100")
                elif price_ratio >= Decimal("5"):
                    valuation_price_local *= Decimal("10")
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
        started_at = perf_counter()
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
        findings: list[FinancialReconciliationFinding] = []
        examined = 0
        for transaction, rule, cashflow in rows:
            examined += 1
            if cashflow is None:
                findings.append(
                    self._build_finding(
                        run_id=run.run_id,
                        reconciliation_type="transaction_cashflow",
                        finding_type="missing_cashflow",
                        severity="ERROR",
                        portfolio_id=transaction.portfolio_id,
                        security_id=transaction.security_id,
                        transaction_id=transaction.transaction_id,
                        business_date=transaction.transaction_date.date(),
                        epoch=request.epoch,
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
                )
                continue

            mismatches: dict[str, tuple[object, object]] = {}
            if cashflow.classification != rule.classification:
                mismatches["classification"] = (rule.classification, cashflow.classification)
            if cashflow.timing != rule.timing:
                mismatches["timing"] = (rule.timing, cashflow.timing)
            if bool(cashflow.is_position_flow) != bool(rule.is_position_flow):
                mismatches["is_position_flow"] = (rule.is_position_flow, cashflow.is_position_flow)
            if bool(cashflow.is_portfolio_flow) != bool(rule.is_portfolio_flow):
                mismatches["is_portfolio_flow"] = (
                    rule.is_portfolio_flow,
                    cashflow.is_portfolio_flow,
                )
            if mismatches:
                findings.append(
                    self._build_finding(
                        run_id=run.run_id,
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
                )

        await self.repository.add_findings(findings)
        summary = self._summary(examined=examined, findings=findings)
        await self.repository.mark_run_completed(run, status="COMPLETED", summary=summary)
        observe_financial_reconciliation_run(
            "transaction_cashflow",
            "COMPLETED",
            perf_counter() - started_at,
            findings,
        )
        return run

    async def run_position_valuation(
        self,
        *,
        request: ReconciliationRunRequest,
        correlation_id: str | None,
    ):
        started_at = perf_counter()
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
            quantity = Decimal(str(snapshot.quantity))
            cost_basis_local = Decimal(str(snapshot.cost_basis_local))
            expected_market_value_local = self._expected_market_value_local(
                quantity=quantity,
                market_price=Decimal(str(snapshot.market_price)),
                cost_basis_local=cost_basis_local,
                product_type=instrument.product_type,
            )
            expected_unrealized = expected_market_value_local - cost_basis_local
            observed_market_value_local = Decimal(str(snapshot.market_value_local))
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

            observed_unrealized = Decimal(str(snapshot.unrealized_gain_loss_local))
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
            perf_counter() - started_at,
            findings,
        )
        return run

    async def run_timeseries_integrity(
        self,
        *,
        request: ReconciliationRunRequest,
        correlation_id: str | None,
    ):
        started_at = perf_counter()
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

        findings: list[FinancialReconciliationFinding] = []
        examined = 0
        if portfolio_by_key:
            all_keys = set(portfolio_by_key)
        else:
            all_keys = set(aggregate_by_key) | set(snapshot_count_by_key)
        for key in sorted(
            all_keys,
            key=lambda item: (item.portfolio_id, item.business_date, item.epoch),
        ):
            examined += 1
            portfolio_row = portfolio_by_key.get(key)
            snapshot_count = snapshot_count_by_key.get(key, 0)

            if portfolio_row is None:
                aggregate_row = aggregate_by_key.get(key)
                if aggregate_row is None:
                    continue
                findings.append(
                    self._build_finding(
                        run_id=run.run_id,
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
                )
                continue

            authoritative_metrics, authoritative_position_count = (
                await self._aggregate_authoritative_portfolio_metrics(
                    portfolio_id=key.portfolio_id,
                    business_date=key.business_date,
                    epoch=key.epoch,
                )
            )
            authoritative_snapshot_count = await self.repository.fetch_authoritative_snapshot_count(
                portfolio_id=key.portfolio_id,
                business_date=key.business_date,
                epoch=key.epoch,
            )

            if authoritative_position_count == 0:
                findings.append(
                    self._build_finding(
                        run_id=run.run_id,
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
                )
                continue

            if not portfolio_by_key:
                snapshot_count = authoritative_snapshot_count or snapshot_count

            if authoritative_position_count != authoritative_snapshot_count:
                findings.append(
                    self._build_finding(
                        run_id=run.run_id,
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
                )

            metric_pairs = {
                "bod_market_value": (
                    Decimal(str(portfolio_row.bod_market_value)),
                    authoritative_metrics["bod_market_value"],
                ),
                "bod_cashflow": (
                    Decimal(str(portfolio_row.bod_cashflow)),
                    authoritative_metrics["bod_cashflow"],
                ),
                "eod_cashflow": (
                    Decimal(str(portfolio_row.eod_cashflow)),
                    authoritative_metrics["eod_cashflow"],
                ),
                "eod_market_value": (
                    Decimal(str(portfolio_row.eod_market_value)),
                    authoritative_metrics["eod_market_value"],
                ),
                "fees": (
                    Decimal(str(portfolio_row.fees)),
                    authoritative_metrics["fees"],
                ),
            }
            mismatches = {}
            for metric_name, (portfolio_value, aggregate_value) in metric_pairs.items():
                delta = portfolio_value - aggregate_value
                if abs(delta) > tolerance:
                    mismatches[metric_name] = {
                        "portfolio_timeseries": str(portfolio_value),
                        "position_aggregate": str(aggregate_value),
                        "delta": str(delta),
                    }
            if mismatches:
                findings.append(
                    self._build_finding(
                        run_id=run.run_id,
                        reconciliation_type="timeseries_integrity",
                        finding_type="portfolio_timeseries_aggregate_mismatch",
                        severity="ERROR",
                        portfolio_id=key.portfolio_id,
                        security_id=None,
                        transaction_id=None,
                        business_date=key.business_date,
                        epoch=key.epoch,
                        expected_value={k: v["position_aggregate"] for k, v in mismatches.items()},
                        observed_value={
                            k: v["portfolio_timeseries"] for k, v in mismatches.items()
                        },
                        detail=mismatches,
                    )
                )

        await self.repository.add_findings(findings)
        summary = self._summary(examined=examined, findings=findings)
        await self.repository.mark_run_completed(run, status="COMPLETED", summary=summary)
        observe_financial_reconciliation_run(
            "timeseries_integrity",
            "COMPLETED",
            perf_counter() - started_at,
            findings,
        )
        return run

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
            finding_id=f"finding-{uuid4().hex}",
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
