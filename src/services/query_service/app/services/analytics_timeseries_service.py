from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

from portfolio_common.analytics_cashflow_semantics import (
    classify_analytics_cash_flow,
    normalize_position_flow_amount,
)
from portfolio_common.monitoring import (
    ANALYTICS_EXPORT_JOB_DURATION_SECONDS,
    ANALYTICS_EXPORT_JOBS_TOTAL,
    ANALYTICS_EXPORT_PAGE_DEPTH,
    ANALYTICS_EXPORT_RESULT_BYTES,
)
from portfolio_common.reconciliation_quality import (
    COMPLETE,
    PARTIAL,
    DataQualityCoverageSignal,
    classify_data_quality_coverage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.analytics_input_dto import (
    AnalyticsExportCreateRequest,
    AnalyticsExportJobResponse,
    AnalyticsExportJsonResultResponse,
    AnalyticsWindow,
    CashFlowObservation,
    LineageMetadata,
    PageMetadata,
    PortfolioAnalyticsReferenceRequest,
    PortfolioAnalyticsReferenceResponse,
    PortfolioAnalyticsTimeseriesRequest,
    PortfolioAnalyticsTimeseriesResponse,
    PortfolioQualityDiagnostics,
    PortfolioTimeseriesObservation,
    PositionAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesResponse,
    PositionTimeseriesRow,
    QualityDiagnostics,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.analytics_export_repository import AnalyticsExportRepository
from ..repositories.analytics_timeseries_repository import AnalyticsTimeseriesRepository
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
from ..settings import load_query_service_settings
from .decimal_amounts import decimal_or_zero
from .request_fingerprint import request_fingerprint


class AnalyticsInputError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PositionPageSupportInputs:
    position_cashflows_by_key: dict[tuple[str, date], list[CashFlowObservation]]
    portfolio_cashflows_by_date: dict[date, list[CashFlowObservation]]
    position_to_portfolio_rates: dict[str, dict[date, Decimal]]
    fx_rates: dict[date, Decimal]
    previous_eod_by_security: dict[str, Decimal]


@dataclass(frozen=True)
class _PositionPageScope:
    page_dates: list[date]
    page_start_date: date
    page_end_date: date
    first_page_date: date
    security_ids: list[str]


@dataclass(frozen=True)
class _PortfolioObservationPageScope:
    page_dates: list[date]
    has_more: bool


@dataclass(frozen=True)
class _PortfolioObservationSupportInputs:
    position_rows: list[object]
    portfolio_cashflows_by_date: dict[date, list[CashFlowObservation]]
    position_cashflows_by_key: dict[tuple[str, date], list[CashFlowObservation]]
    position_to_portfolio_rates: dict[str, dict[date, Decimal]]
    portfolio_to_reporting_rates: dict[date, Decimal]
    previous_eod_by_security: dict[str, Decimal]


class AnalyticsTimeseriesService:
    _EXPORT_LIFECYCLE_MODE = "inline_job_execution"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AnalyticsTimeseriesRepository(db)
        self.export_repo = AnalyticsExportRepository(db)
        settings = load_query_service_settings()
        self._page_token_secret = settings.page_token_secret
        self._analytics_export_stale_timeout_minutes = (
            settings.analytics_export_stale_timeout_minutes
        )

    def _request_fingerprint(self, payload: dict) -> str:
        return request_fingerprint(payload)

    def _encode_page_token(self, payload: dict) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(
            self._page_token_secret.encode("utf-8"),
            serialized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        envelope = {"p": payload, "s": signature}
        return base64.urlsafe_b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")

    def _decode_page_token(self, token: str | None) -> dict:
        if not token:
            return {}
        try:
            decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
            envelope = json.loads(decoded)
            payload = envelope["p"]
            signature = envelope["s"]
            serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            expected = hmac.new(
                self._page_token_secret.encode("utf-8"),
                serialized.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise AnalyticsInputError("INVALID_REQUEST", "Invalid page token signature.")
            return payload
        except AnalyticsInputError:
            raise
        except Exception as exc:
            raise AnalyticsInputError("INVALID_REQUEST", "Malformed page token.") from exc

    def _resolve_window(
        self,
        *,
        as_of_date: date,
        window: AnalyticsWindow | None,
        period: str | None,
        inception_date: date,
    ) -> AnalyticsWindow:
        if window is not None:
            return self._bounded_explicit_window(window=window, as_of_date=as_of_date)

        return AnalyticsWindow(
            start_date=self._clamped_period_start_date(
                as_of_date=as_of_date,
                period=period,
                inception_date=inception_date,
            ),
            end_date=as_of_date,
        )

    @staticmethod
    def _bounded_explicit_window(
        *,
        window: AnalyticsWindow,
        as_of_date: date,
    ) -> AnalyticsWindow:
        end_date = min(window.end_date, as_of_date)
        if window.start_date > end_date:
            raise AnalyticsInputError(
                "INVALID_REQUEST", "window.start_date must be before or equal to end_date."
            )
        return AnalyticsWindow(start_date=window.start_date, end_date=end_date)

    @staticmethod
    def _clamped_period_start_date(
        *,
        as_of_date: date,
        period: str | None,
        inception_date: date,
    ) -> date:
        start_date = AnalyticsTimeseriesService._period_start_date(
            as_of_date=as_of_date,
            period=period,
            inception_date=inception_date,
        )
        return max(start_date, inception_date)

    @staticmethod
    def _period_start_date(
        *,
        as_of_date: date,
        period: str | None,
        inception_date: date,
    ) -> date:
        period_start_dates = {
            "one_month": as_of_date - timedelta(days=31),
            "three_months": as_of_date - timedelta(days=92),
            "ytd": date(as_of_date.year, 1, 1),
            "one_year": as_of_date - timedelta(days=365),
            "three_years": as_of_date - timedelta(days=365 * 3),
            "five_years": as_of_date - timedelta(days=365 * 5),
            "inception": inception_date,
        }
        if period not in period_start_dates:
            raise AnalyticsInputError("INVALID_REQUEST", "Unsupported period value.")
        return period_start_dates[period]

    async def _get_conversion_rates(
        self,
        *,
        portfolio_currency: str,
        reporting_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        normalized_portfolio_currency = normalize_currency_code(portfolio_currency)
        normalized_reporting_currency = normalize_currency_code(reporting_currency)
        if normalized_portfolio_currency == normalized_reporting_currency:
            return {}
        return await self.repo.get_fx_rates_map(
            from_currency=normalized_portfolio_currency,
            to_currency=normalized_reporting_currency,
            start_date=start_date,
            end_date=end_date,
        )

    async def _get_position_to_portfolio_rate_maps(
        self,
        *,
        position_currencies: set[str],
        portfolio_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, dict[date, Decimal]]:
        normalized_portfolio_currency = normalize_currency_code(portfolio_currency)
        normalized_position_currencies = {
            normalize_currency_code(position_currency)
            for position_currency in position_currencies
            if position_currency
        }
        rates: dict[str, dict[date, Decimal]] = {}
        for position_currency in sorted(normalized_position_currencies):
            if position_currency == normalized_portfolio_currency:
                rates[position_currency] = {}
                continue
            rates[position_currency] = await self.repo.get_fx_rates_map(
                from_currency=position_currency,
                to_currency=normalized_portfolio_currency,
                start_date=start_date,
                end_date=end_date,
            )
        return rates

    @staticmethod
    def _quality_status_from_epoch(epoch: int) -> str:
        if epoch > 0:
            return "restated"
        return "final"

    @staticmethod
    def _build_cash_flow_observation(
        row: object,
        *,
        amount: Decimal,
    ) -> CashFlowObservation:
        cash_flow_type, flow_scope = classify_analytics_cash_flow(
            classification=str(row.classification),
            is_position_flow=bool(row.is_position_flow),
            is_portfolio_flow=bool(row.is_portfolio_flow),
        )
        return CashFlowObservation(
            amount=amount,
            timing=str(row.timing).strip().lower(),
            cash_flow_type=cash_flow_type,
            flow_scope=flow_scope,
            source_classification=str(row.classification),
        )

    def _portfolio_cash_flows_for_dates(
        self,
        cashflow_rows: list[object],
        *,
        reporting_currency: str,
        portfolio_currency: str,
        fx_rates: dict[date, Decimal],
    ) -> dict[date, list[CashFlowObservation]]:
        normalized_reporting_currency = normalize_currency_code(reporting_currency)
        normalized_portfolio_currency = normalize_currency_code(portfolio_currency)
        flows_by_date: dict[date, list[CashFlowObservation]] = defaultdict(list)
        for row in cashflow_rows:
            conversion_rate = Decimal("1")
            if normalized_reporting_currency != normalized_portfolio_currency:
                valuation_date = row.valuation_date
                if valuation_date not in fx_rates:
                    raise AnalyticsInputError(
                        "INSUFFICIENT_DATA",
                        "Missing FX rate for "
                        f"{normalized_portfolio_currency}/{normalized_reporting_currency} "
                        f"on {valuation_date}.",
                    )
                conversion_rate = fx_rates[valuation_date]
            flows_by_date[row.valuation_date].append(
                self._build_cash_flow_observation(
                    row,
                    amount=decimal_or_zero(row.amount) * conversion_rate,
                )
            )
        return flows_by_date

    def _position_cash_flows_for_keys(
        self,
        cashflow_rows: list[object],
    ) -> dict[tuple[str, date], list[CashFlowObservation]]:
        flows_by_key: dict[tuple[str, date], list[CashFlowObservation]] = defaultdict(list)
        for row in cashflow_rows:
            amount = decimal_or_zero(row.amount)
            if bool(row.is_position_flow):
                amount = normalize_position_flow_amount(
                    amount=amount,
                    classification=str(row.classification),
                )
            flows_by_key[(normalize_security_id(row.security_id), row.valuation_date)].append(
                self._build_cash_flow_observation(row, amount=amount)
            )
        return flows_by_key

    @staticmethod
    def _has_external_flow(cash_flows: list[CashFlowObservation]) -> bool:
        return any(flow.flow_scope == "external" for flow in cash_flows)

    @staticmethod
    def _has_only_internal_flows(cash_flows: list[CashFlowObservation]) -> bool:
        return bool(cash_flows) and all(flow.flow_scope == "internal" for flow in cash_flows)

    @staticmethod
    def _is_cash_book_position(row: object) -> bool:
        asset_class = str(getattr(row, "asset_class", "") or "").strip().casefold()
        security_id = str(getattr(row, "security_id", "") or "").strip().upper()
        return asset_class == "cash" or security_id.startswith("CASH_")

    @staticmethod
    def _effective_beginning_market_value(
        row: object,
        *,
        previous_eod_market_value: Decimal | None,
        cash_flows: list[CashFlowObservation],
        has_portfolio_external_flow: bool,
    ) -> Decimal:
        stored_beginning = decimal_or_zero(row.bod_market_value)
        ending = decimal_or_zero(row.eod_market_value)
        bod_position_flow = decimal_or_zero(getattr(row, "bod_cashflow_position", 0))

        if AnalyticsTimeseriesService._has_prior_eod_continuity(
            previous_eod_market_value=previous_eod_market_value,
            bod_position_flow=bod_position_flow,
        ):
            return previous_eod_market_value

        has_internal_position_flow = AnalyticsTimeseriesService._has_only_internal_flows(cash_flows)
        if AnalyticsTimeseriesService._is_internal_cash_book_settlement(
            row=row,
            has_portfolio_external_flow=has_portfolio_external_flow,
            has_internal_position_flow=has_internal_position_flow,
        ):
            return ending

        if AnalyticsTimeseriesService._can_repair_beginning_from_previous_eod(
            previous_eod_market_value=previous_eod_market_value,
            stored_beginning=stored_beginning,
            bod_position_flow=bod_position_flow,
            has_portfolio_external_flow=has_portfolio_external_flow,
            has_internal_position_flow=has_internal_position_flow,
        ):
            return previous_eod_market_value + bod_position_flow

        if AnalyticsTimeseriesService._is_new_internally_funded_position(
            previous_eod_market_value=previous_eod_market_value,
            ending=ending,
            has_portfolio_external_flow=has_portfolio_external_flow,
            has_internal_position_flow=has_internal_position_flow,
        ):
            return ending

        return stored_beginning

    @staticmethod
    def _has_prior_eod_continuity(
        *,
        previous_eod_market_value: Decimal | None,
        bod_position_flow: Decimal,
    ) -> bool:
        return (
            previous_eod_market_value is not None
            and previous_eod_market_value != 0
            and bod_position_flow == 0
        )

    @staticmethod
    def _is_internal_cash_book_settlement(
        *,
        row: object,
        has_portfolio_external_flow: bool,
        has_internal_position_flow: bool,
    ) -> bool:
        return (
            AnalyticsTimeseriesService._is_cash_book_position(row)
            and not has_portfolio_external_flow
            and has_internal_position_flow
        )

    @staticmethod
    def _can_repair_beginning_from_previous_eod(
        *,
        previous_eod_market_value: Decimal | None,
        stored_beginning: Decimal,
        bod_position_flow: Decimal,
        has_portfolio_external_flow: bool,
        has_internal_position_flow: bool,
    ) -> bool:
        return (
            previous_eod_market_value is not None
            and stored_beginning == 0
            and bod_position_flow != 0
            and not has_portfolio_external_flow
            and has_internal_position_flow
        )

    @staticmethod
    def _is_new_internally_funded_position(
        *,
        previous_eod_market_value: Decimal | None,
        ending: Decimal,
        has_portfolio_external_flow: bool,
        has_internal_position_flow: bool,
    ) -> bool:
        no_prior_capital = previous_eod_market_value is None or previous_eod_market_value == 0
        return (
            no_prior_capital
            and ending != 0
            and (not has_portfolio_external_flow and has_internal_position_flow)
        )

    async def _portfolio_observation_rows(
        self,
        *,
        portfolio_id: str,
        portfolio_currency: str,
        reporting_currency: str,
        resolved_window: AnalyticsWindow,
        page_size: int,
        cursor_date: date | None,
        request_scope_fingerprint: str,
    ) -> tuple[list[PortfolioTimeseriesObservation], dict[str, int], list[date], int, str | None]:
        portfolio_currency = normalize_currency_code(portfolio_currency)
        reporting_currency = normalize_currency_code(reporting_currency)
        snapshot_epoch = await self.repo.get_position_snapshot_epoch(
            portfolio_id=portfolio_id,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
            security_ids=[],
            position_ids=[],
            dimension_filters={},
        )
        observed_dates = await self.repo.list_position_observation_dates(
            portfolio_id=portfolio_id,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
            snapshot_epoch=snapshot_epoch,
        )
        page_scope = self._portfolio_observation_page_scope(
            observed_dates=observed_dates,
            cursor_date=cursor_date,
            page_size=page_size,
        )
        if not page_scope.page_dates:
            return [], {}, observed_dates, snapshot_epoch, None

        support_inputs = await self._portfolio_observation_support_inputs(
            portfolio_id=portfolio_id,
            page_dates=page_scope.page_dates,
            snapshot_epoch=snapshot_epoch,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
        )
        observations, quality_distribution = self._portfolio_observations_for_page(
            page_dates=page_scope.page_dates,
            support_inputs=support_inputs,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
        )
        next_page_token = self._portfolio_observation_next_page_token(
            page_scope=page_scope,
            snapshot_epoch=snapshot_epoch,
            request_scope_fingerprint=request_scope_fingerprint,
        )
        return observations, quality_distribution, observed_dates, snapshot_epoch, next_page_token

    @staticmethod
    def _portfolio_observation_page_scope(
        *,
        observed_dates: list[date],
        cursor_date: date | None,
        page_size: int,
    ) -> _PortfolioObservationPageScope:
        paged_dates = [day for day in observed_dates if cursor_date is None or day > cursor_date]
        return _PortfolioObservationPageScope(
            page_dates=paged_dates[:page_size],
            has_more=len(paged_dates) > page_size,
        )

    async def _portfolio_observation_support_inputs(
        self,
        *,
        portfolio_id: str,
        page_dates: list[date],
        snapshot_epoch: int,
        portfolio_currency: str,
        reporting_currency: str,
    ) -> _PortfolioObservationSupportInputs:
        page_start_date = min(page_dates)
        page_end_date = max(page_dates)
        position_rows = await self.repo.list_position_timeseries_rows_unpaged(
            portfolio_id=portfolio_id,
            start_date=page_start_date,
            end_date=page_end_date,
            snapshot_epoch=snapshot_epoch,
        )
        normalized_security_ids = self._portfolio_position_security_ids(position_rows)
        position_to_portfolio_rates = await self._get_position_to_portfolio_rate_maps(
            position_currencies=self._portfolio_position_currencies(position_rows),
            portfolio_currency=portfolio_currency,
            start_date=page_start_date,
            end_date=page_end_date,
        )
        portfolio_to_reporting_rates = await self._get_conversion_rates(
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            start_date=page_start_date,
            end_date=page_end_date,
        )
        portfolio_cashflow_rows = await self.repo.list_portfolio_cashflow_rows(
            portfolio_id=portfolio_id,
            valuation_dates=page_dates,
            snapshot_epoch=snapshot_epoch,
        )
        position_cashflow_rows = await self.repo.list_position_cashflow_rows(
            portfolio_id=portfolio_id,
            security_ids=normalized_security_ids,
            valuation_dates=page_dates,
            snapshot_epoch=snapshot_epoch,
        )
        previous_rows = await self.repo.list_latest_position_timeseries_before(
            portfolio_id=portfolio_id,
            before_date=page_dates[0],
            security_ids=normalized_security_ids,
            snapshot_epoch=snapshot_epoch,
        )
        return _PortfolioObservationSupportInputs(
            position_rows=position_rows,
            portfolio_cashflows_by_date=self._portfolio_cash_flows_for_dates(
                portfolio_cashflow_rows,
                reporting_currency=reporting_currency,
                portfolio_currency=portfolio_currency,
                fx_rates=portfolio_to_reporting_rates,
            ),
            position_cashflows_by_key=self._position_cash_flows_for_keys(position_cashflow_rows),
            position_to_portfolio_rates=position_to_portfolio_rates,
            portfolio_to_reporting_rates=portfolio_to_reporting_rates,
            previous_eod_by_security=self._previous_eod_by_security(previous_rows),
        )

    @staticmethod
    def _portfolio_position_currencies(position_rows: list[object]) -> set[str]:
        return {
            str(row.position_currency)
            for row in position_rows
            if getattr(row, "position_currency", None)
        }

    @staticmethod
    def _portfolio_position_security_ids(position_rows: list[object]) -> list[str]:
        return sorted(
            {
                security_id
                for row in position_rows
                if (security_id := normalize_security_id(row.security_id))
            }
        )

    @staticmethod
    def _previous_eod_by_security(previous_rows: list[object]) -> dict[str, Decimal]:
        return {
            normalize_security_id(row.security_id): decimal_or_zero(row.eod_market_value)
            for row in previous_rows
        }

    def _portfolio_observations_for_page(
        self,
        *,
        page_dates: list[date],
        support_inputs: _PortfolioObservationSupportInputs,
        portfolio_currency: str,
        reporting_currency: str,
    ) -> tuple[list[PortfolioTimeseriesObservation], dict[str, int]]:
        observations: list[PortfolioTimeseriesObservation] = []
        quality_distribution: dict[str, int] = {}
        previous_eod_by_security = dict(support_inputs.previous_eod_by_security)
        row_buckets = self._portfolio_row_buckets(
            page_dates=page_dates,
            position_rows=support_inputs.position_rows,
        )
        for valuation_date in page_dates:
            observation, quality, previous_eod_by_security = self._portfolio_observation_for_date(
                valuation_date=valuation_date,
                rows=row_buckets.get(valuation_date, []),
                support_inputs=support_inputs,
                previous_eod_by_security=previous_eod_by_security,
                portfolio_currency=portfolio_currency,
                reporting_currency=reporting_currency,
            )
            quality_distribution[quality] = quality_distribution.get(quality, 0) + 1
            observations.append(observation)
        return observations, quality_distribution

    @staticmethod
    def _portfolio_row_buckets(
        *,
        page_dates: list[date],
        position_rows: list[object],
    ) -> dict[date, list[object]]:
        page_date_set = set(page_dates)
        row_buckets: dict[date, list[object]] = defaultdict(list)
        for row in position_rows:
            if row.valuation_date in page_date_set:
                row_buckets[row.valuation_date].append(row)
        return row_buckets

    def _portfolio_observation_for_date(
        self,
        *,
        valuation_date: date,
        rows: list[object],
        support_inputs: _PortfolioObservationSupportInputs,
        previous_eod_by_security: dict[str, Decimal],
        portfolio_currency: str,
        reporting_currency: str,
    ) -> tuple[PortfolioTimeseriesObservation, str, dict[str, Decimal]]:
        conversion_rate = self._portfolio_to_reporting_observation_rate(
            valuation_date=valuation_date,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            portfolio_to_reporting_rates=support_inputs.portfolio_to_reporting_rates,
        )
        beginning_market_value = Decimal("0")
        ending_market_value = Decimal("0")
        quality = "final"
        portfolio_cashflows = support_inputs.portfolio_cashflows_by_date.get(valuation_date, [])
        has_portfolio_external_flow = self._has_external_flow(portfolio_cashflows)
        current_eod_by_security: dict[str, Decimal] = {}
        for row in rows:
            security_id = normalize_security_id(row.security_id)
            position_to_portfolio_rate = self._position_to_portfolio_observation_rate(
                row=row,
                valuation_date=valuation_date,
                portfolio_currency=portfolio_currency,
                position_to_portfolio_rates=support_inputs.position_to_portfolio_rates,
            )
            cash_flows = support_inputs.position_cashflows_by_key.get(
                (security_id, valuation_date), []
            )
            beginning_market_value += (
                self._effective_beginning_market_value(
                    row,
                    previous_eod_market_value=previous_eod_by_security.get(security_id),
                    cash_flows=cash_flows,
                    has_portfolio_external_flow=has_portfolio_external_flow,
                )
                * position_to_portfolio_rate
                * conversion_rate
            )
            ending_eod = decimal_or_zero(row.eod_market_value)
            ending_market_value += ending_eod * position_to_portfolio_rate * conversion_rate
            current_eod_by_security[security_id] = ending_eod
            if int(row.epoch) > 0:
                quality = "restated"
        return (
            PortfolioTimeseriesObservation(
                valuation_date=valuation_date,
                beginning_market_value=beginning_market_value,
                ending_market_value=ending_market_value,
                valuation_status=quality,
                cash_flows=portfolio_cashflows,
                cash_flow_currency=reporting_currency,
            ),
            quality,
            current_eod_by_security,
        )

    @staticmethod
    def _portfolio_to_reporting_observation_rate(
        *,
        valuation_date: date,
        portfolio_currency: str,
        reporting_currency: str,
        portfolio_to_reporting_rates: dict[date, Decimal],
    ) -> Decimal:
        if reporting_currency == portfolio_currency:
            return Decimal("1")
        if valuation_date not in portfolio_to_reporting_rates:
            raise AnalyticsInputError(
                "INSUFFICIENT_DATA",
                "Missing FX rate for "
                f"{portfolio_currency}/{reporting_currency} on {valuation_date}.",
            )
        return portfolio_to_reporting_rates[valuation_date]

    @staticmethod
    def _position_to_portfolio_observation_rate(
        *,
        row: object,
        valuation_date: date,
        portfolio_currency: str,
        position_to_portfolio_rates: dict[str, dict[date, Decimal]],
    ) -> Decimal:
        position_currency = (
            normalize_currency_code(str(getattr(row, "position_currency")))
            if getattr(row, "position_currency", None)
            else ""
        )
        if not position_currency or position_currency == portfolio_currency:
            return Decimal("1")
        rate_map = position_to_portfolio_rates.get(position_currency, {})
        if valuation_date not in rate_map:
            raise AnalyticsInputError(
                "INSUFFICIENT_DATA",
                "Missing FX rate for "
                f"{position_currency}/{portfolio_currency} on {valuation_date}.",
            )
        return rate_map[valuation_date]

    def _portfolio_observation_next_page_token(
        self,
        *,
        page_scope: _PortfolioObservationPageScope,
        snapshot_epoch: int,
        request_scope_fingerprint: str,
    ) -> str | None:
        if not page_scope.has_more:
            return None
        return self._encode_page_token(
            {
                "valuation_date": page_scope.page_dates[-1].isoformat(),
                "snapshot_epoch": snapshot_epoch,
                "scope_fingerprint": request_scope_fingerprint,
            }
        )

    async def get_portfolio_timeseries(
        self,
        *,
        portfolio_id: str,
        request: PortfolioAnalyticsTimeseriesRequest,
    ) -> PortfolioAnalyticsTimeseriesResponse:
        portfolio = await self.repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")
        portfolio_currency = normalize_currency_code(str(portfolio.base_currency))

        resolved_window = self._resolve_window(
            as_of_date=request.as_of_date,
            window=request.window,
            period=request.period,
            inception_date=portfolio.open_date,
        )
        reporting_currency = normalize_currency_code(
            str(request.reporting_currency or portfolio_currency)
        )
        request_scope_fingerprint = self._portfolio_timeseries_scope_fingerprint(
            portfolio_id=portfolio_id,
            request=request,
            resolved_window=resolved_window,
            reporting_currency=reporting_currency,
        )
        cursor_date = self._portfolio_timeseries_cursor_date(
            page_token=request.page.page_token,
            request_scope_fingerprint=request_scope_fingerprint,
        )
        expected_business_dates = await self.repo.list_business_dates(
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
        )
        (
            observations,
            quality_distribution,
            observed_dates,
            snapshot_epoch,
            next_page_token,
        ) = await self._portfolio_observation_rows(
            portfolio_id=portfolio_id,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            resolved_window=resolved_window,
            page_size=request.page.page_size,
            cursor_date=cursor_date,
            request_scope_fingerprint=request_scope_fingerprint,
        )

        latest_date = await self._latest_available_performance_date(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            observed_dates=observed_dates,
        )
        diagnostics = self._portfolio_timeseries_diagnostics(
            quality_distribution=quality_distribution,
            expected_business_dates=expected_business_dates,
            observed_dates=observed_dates,
        )
        data_quality_status = self._timeseries_data_quality_status(
            required_count=len(expected_business_dates),
            observed_count=len(observed_dates),
            stale_count=diagnostics.stale_points_count,
            warning_issue_count=1 if next_page_token else 0,
        )
        fingerprint = self._request_fingerprint(
            {
                "endpoint": "portfolio-timeseries",
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
            }
        )
        generated_at = datetime.now(UTC)
        return PortfolioAnalyticsTimeseriesResponse(
            portfolio_id=portfolio_id,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            portfolio_open_date=portfolio.open_date,
            portfolio_close_date=portfolio.close_date,
            performance_end_date=latest_date,
            resolved_window=resolved_window,
            frequency=request.frequency,
            lineage=LineageMetadata(
                generated_by="integration.analytics_inputs",
                generated_at=generated_at,
                request_fingerprint=fingerprint,
                data_version="state_inputs_v1",
            ),
            diagnostics=diagnostics,
            page=PageMetadata(
                page_size=request.page.page_size,
                returned_row_count=len(observations),
                sort_key="valuation_date:asc",
                request_scope_fingerprint=request_scope_fingerprint,
                snapshot_epoch=snapshot_epoch,
                next_page_token=next_page_token,
            ),
            observations=observations,
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=generated_at,
                data_quality_status=data_quality_status,
            ),
        )

    def _portfolio_timeseries_scope_fingerprint(
        self,
        *,
        portfolio_id: str,
        request: PortfolioAnalyticsTimeseriesRequest,
        resolved_window: AnalyticsWindow,
        reporting_currency: str,
    ) -> str:
        return self._request_fingerprint(
            {
                "endpoint": "portfolio-timeseries",
                "portfolio_id": portfolio_id,
                "as_of_date": request.as_of_date.isoformat(),
                "resolved_window": resolved_window.model_dump(mode="json"),
                "frequency": request.frequency,
                "reporting_currency": reporting_currency,
            }
        )

    def _portfolio_timeseries_cursor_date(
        self,
        *,
        page_token: str | None,
        request_scope_fingerprint: str,
    ) -> date | None:
        cursor = self._decode_page_token(page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope is not None and token_scope != request_scope_fingerprint:
            raise AnalyticsInputError("INVALID_REQUEST", "Page token does not match request scope.")
        if not cursor.get("valuation_date"):
            return None
        return date.fromisoformat(cursor["valuation_date"])

    @staticmethod
    def _portfolio_timeseries_diagnostics(
        *,
        quality_distribution: dict[str, int],
        expected_business_dates: list[date],
        observed_dates: list[date],
    ) -> PortfolioQualityDiagnostics:
        observed_date_set = set(observed_dates)
        missing_dates_count = sum(
            1 for expected_date in expected_business_dates if expected_date not in observed_date_set
        )
        stale_points_count = sum(
            count for status_name, count in quality_distribution.items() if status_name != "final"
        )
        return PortfolioQualityDiagnostics(
            quality_status_distribution=quality_distribution,
            missing_dates_count=missing_dates_count,
            stale_points_count=stale_points_count,
            expected_business_dates_count=len(expected_business_dates),
            returned_observation_dates_count=len(observed_dates),
            cash_flows_included=True,
        )

    async def get_position_timeseries(
        self,
        *,
        portfolio_id: str,
        request: PositionAnalyticsTimeseriesRequest,
    ) -> PositionAnalyticsTimeseriesResponse:
        portfolio = await self.repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")
        portfolio_currency = normalize_currency_code(str(portfolio.base_currency))
        resolved_window = self._resolve_window(
            as_of_date=request.as_of_date,
            window=request.window,
            period=request.period,
            inception_date=portfolio.open_date,
        )
        reporting_currency = normalize_currency_code(
            str(request.reporting_currency or portfolio_currency)
        )
        request_scope_fingerprint = self._request_fingerprint(
            {
                "endpoint": "position-timeseries",
                "portfolio_id": portfolio_id,
                "as_of_date": request.as_of_date.isoformat(),
                "resolved_window": resolved_window.model_dump(mode="json"),
                "frequency": request.frequency,
                "reporting_currency": reporting_currency,
                "security_ids": request.filters.security_ids,
                "position_ids": request.filters.position_ids,
                "dimension_filters": [
                    f.model_dump(mode="json") for f in request.filters.dimension_filters
                ],
                "dimensions": request.dimensions,
                "include_cash_flows": request.include_cash_flows,
            }
        )
        cursor = self._decode_page_token(request.page.page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope is not None and token_scope != request_scope_fingerprint:
            raise AnalyticsInputError("INVALID_REQUEST", "Page token does not match request scope.")
        cursor_date = (
            date.fromisoformat(cursor["valuation_date"]) if cursor.get("valuation_date") else None
        )
        cursor_security_id = cursor.get("security_id")
        dimension_filters = {
            item.dimension: set(item.values) for item in request.filters.dimension_filters
        }
        snapshot_epoch = int(cursor["snapshot_epoch"]) if cursor.get("snapshot_epoch") else None
        if snapshot_epoch is None:
            snapshot_epoch = await self.repo.get_position_snapshot_epoch(
                portfolio_id=portfolio_id,
                start_date=resolved_window.start_date,
                end_date=resolved_window.end_date,
                security_ids=request.filters.security_ids,
                position_ids=request.filters.position_ids,
                dimension_filters=dimension_filters,
            )
        rows = await self.repo.list_position_timeseries_rows(
            portfolio_id=portfolio_id,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
            page_size=request.page.page_size,
            cursor_date=cursor_date,
            cursor_security_id=cursor_security_id,
            security_ids=request.filters.security_ids,
            position_ids=request.filters.position_ids,
            dimension_filters=dimension_filters,
            snapshot_epoch=snapshot_epoch,
        )
        has_more = len(rows) > request.page.page_size
        rows_page = rows[: request.page.page_size]
        support_inputs = await self._position_page_support_inputs(
            portfolio_id=portfolio_id,
            rows_page=rows_page,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            include_cash_flows=request.include_cash_flows,
            snapshot_epoch=snapshot_epoch,
            fallback_start_date=resolved_window.start_date,
        )
        response_rows, quality_distribution = self._position_response_rows(
            portfolio_id=portfolio_id,
            rows_page=rows_page,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            dimensions=request.dimensions,
            include_cash_flows=request.include_cash_flows,
            support_inputs=support_inputs,
        )

        next_page_token: str | None = None
        if has_more and rows_page:
            last = rows_page[-1]
            next_page_token = self._encode_page_token(
                {
                    "valuation_date": last.valuation_date.isoformat(),
                    "security_id": normalize_security_id(last.security_id),
                    "snapshot_epoch": snapshot_epoch,
                    "scope_fingerprint": request_scope_fingerprint,
                }
            )

        stale_points_count = sum(
            count for status_name, count in quality_distribution.items() if status_name != "final"
        )
        data_quality_status = self._timeseries_data_quality_status(
            required_count=len(response_rows),
            observed_count=len(response_rows),
            stale_count=stale_points_count,
            warning_issue_count=1 if next_page_token else 0,
        )

        fingerprint = self._request_fingerprint(
            {
                "endpoint": "position-timeseries",
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
            }
        )
        generated_at = datetime.now(UTC)
        return PositionAnalyticsTimeseriesResponse(
            portfolio_id=portfolio_id,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            resolved_window=resolved_window,
            frequency=request.frequency,
            lineage=LineageMetadata(
                generated_by="integration.analytics_inputs",
                generated_at=generated_at,
                request_fingerprint=fingerprint,
                data_version="state_inputs_v1",
            ),
            diagnostics=QualityDiagnostics(
                quality_status_distribution=quality_distribution,
                missing_dates_count=0,
                stale_points_count=stale_points_count,
                requested_dimensions=list(request.dimensions),
                cash_flows_included=request.include_cash_flows,
            ),
            page=PageMetadata(
                page_size=request.page.page_size,
                returned_row_count=len(response_rows),
                sort_key="valuation_date:asc,security_id:asc",
                request_scope_fingerprint=request_scope_fingerprint,
                snapshot_epoch=snapshot_epoch,
                next_page_token=next_page_token,
            ),
            rows=response_rows,
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=generated_at,
                data_quality_status=data_quality_status,
            ),
        )

    async def _position_page_support_inputs(
        self,
        *,
        portfolio_id: str,
        rows_page: list[object],
        portfolio_currency: str,
        reporting_currency: str,
        include_cash_flows: bool,
        snapshot_epoch: int,
        fallback_start_date: date,
    ) -> _PositionPageSupportInputs:
        if not rows_page:
            return _PositionPageSupportInputs({}, {}, {}, {}, {})

        page_scope = self._position_page_scope(
            rows_page=rows_page,
            fallback_start_date=fallback_start_date,
        )
        portfolio_cashflow_rows = await self.repo.list_portfolio_cashflow_rows(
            portfolio_id=portfolio_id,
            valuation_dates=page_scope.page_dates,
            snapshot_epoch=snapshot_epoch,
        )
        position_to_portfolio_rates = await self._get_position_to_portfolio_rate_maps(
            position_currencies={str(row.position_currency or "") for row in rows_page},
            portfolio_currency=portfolio_currency,
            start_date=page_scope.page_start_date,
            end_date=page_scope.page_end_date,
        )
        fx_rates = await self._get_conversion_rates(
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            start_date=page_scope.page_start_date,
            end_date=page_scope.page_end_date,
        )
        previous_rows = await self.repo.list_latest_position_timeseries_before(
            portfolio_id=portfolio_id,
            before_date=page_scope.first_page_date,
            security_ids=page_scope.security_ids,
            snapshot_epoch=snapshot_epoch,
        )
        position_cashflows_by_key = await self._position_page_cash_flows_by_key(
            portfolio_id=portfolio_id,
            security_ids=page_scope.security_ids,
            page_dates=page_scope.page_dates,
            snapshot_epoch=snapshot_epoch,
            include_cash_flows=include_cash_flows,
        )
        return _PositionPageSupportInputs(
            position_cashflows_by_key=position_cashflows_by_key,
            portfolio_cashflows_by_date=self._portfolio_cash_flows_for_dates(
                portfolio_cashflow_rows,
                reporting_currency=portfolio_currency,
                portfolio_currency=portfolio_currency,
                fx_rates={},
            ),
            position_to_portfolio_rates=position_to_portfolio_rates,
            fx_rates=fx_rates,
            previous_eod_by_security=self._previous_position_eod_by_security(
                previous_rows=previous_rows,
                first_page_date=page_scope.first_page_date,
            ),
        )

    @staticmethod
    def _position_page_scope(
        *,
        rows_page: list[object],
        fallback_start_date: date,
    ) -> _PositionPageScope:
        page_dates = sorted({row.valuation_date for row in rows_page})
        return _PositionPageScope(
            page_dates=page_dates,
            page_start_date=min(page_dates, default=fallback_start_date),
            page_end_date=max(page_dates, default=fallback_start_date),
            first_page_date=min(row.valuation_date for row in rows_page),
            security_ids=sorted(
                {
                    security_id
                    for row in rows_page
                    if (security_id := normalize_security_id(row.security_id))
                }
            ),
        )

    @staticmethod
    def _previous_position_eod_by_security(
        *,
        previous_rows: list[object],
        first_page_date: date,
    ) -> dict[str, Decimal]:
        previous_date = first_page_date - timedelta(days=1)
        return {
            normalize_security_id(row.security_id): decimal_or_zero(row.eod_market_value)
            for row in previous_rows
            if row.valuation_date == previous_date
        }

    async def _position_page_cash_flows_by_key(
        self,
        *,
        portfolio_id: str,
        security_ids: list[str],
        page_dates: list[date],
        snapshot_epoch: int,
        include_cash_flows: bool,
    ) -> dict[tuple[str, date], list[CashFlowObservation]]:
        if not include_cash_flows:
            return {}
        position_cashflow_rows = await self.repo.list_position_cashflow_rows(
            portfolio_id=portfolio_id,
            security_ids=security_ids,
            valuation_dates=page_dates,
            snapshot_epoch=snapshot_epoch,
        )
        return self._position_cash_flows_for_keys(position_cashflow_rows)

    def _position_response_rows(
        self,
        *,
        portfolio_id: str,
        rows_page: list[object],
        portfolio_currency: str,
        reporting_currency: str,
        dimensions: list[str],
        include_cash_flows: bool,
        support_inputs: _PositionPageSupportInputs,
    ) -> tuple[list[PositionTimeseriesRow], dict[str, int]]:
        quality_distribution: dict[str, int] = {}
        response_rows: list[PositionTimeseriesRow] = []
        previous_eod_by_security = dict(support_inputs.previous_eod_by_security)
        current_valuation_date: date | None = None
        current_eod_by_security: dict[str, Decimal] = {}
        for row in rows_page:
            if current_valuation_date is None:
                current_valuation_date = row.valuation_date
            elif row.valuation_date != current_valuation_date:
                previous_eod_by_security = current_eod_by_security
                current_eod_by_security = {}
                current_valuation_date = row.valuation_date

            response_row = self._position_response_row(
                portfolio_id=portfolio_id,
                row=row,
                portfolio_currency=portfolio_currency,
                reporting_currency=reporting_currency,
                dimensions=dimensions,
                include_cash_flows=include_cash_flows,
                support_inputs=support_inputs,
                previous_eod_by_security=previous_eod_by_security,
            )
            quality_distribution[response_row.valuation_status] = (
                quality_distribution.get(response_row.valuation_status, 0) + 1
            )
            response_rows.append(response_row)
            current_eod_by_security[response_row.security_id] = (
                response_row.ending_market_value_position_currency
            )
        return response_rows, quality_distribution

    def _position_response_row(
        self,
        *,
        portfolio_id: str,
        row: object,
        portfolio_currency: str,
        reporting_currency: str,
        dimensions: list[str],
        include_cash_flows: bool,
        support_inputs: _PositionPageSupportInputs,
        previous_eod_by_security: dict[str, Decimal],
    ) -> PositionTimeseriesRow:
        quality = self._quality_status_from_epoch(int(row.epoch))
        position_currency = (
            normalize_currency_code(str(row.position_currency))
            if row.position_currency
            else portfolio_currency
        )
        position_to_portfolio_rate = self._position_to_portfolio_rate(
            position_currency=position_currency,
            portfolio_currency=portfolio_currency,
            valuation_date=row.valuation_date,
            position_to_portfolio_rates=support_inputs.position_to_portfolio_rates,
        )
        portfolio_to_reporting_rate = self._portfolio_to_reporting_rate(
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            valuation_date=row.valuation_date,
            fx_rates=support_inputs.fx_rates,
        )
        security_id = normalize_security_id(row.security_id)
        cash_flows = (
            support_inputs.position_cashflows_by_key.get((security_id, row.valuation_date), [])
            if include_cash_flows
            else []
        )
        beginning_market_value_position = self._effective_beginning_market_value(
            row,
            previous_eod_market_value=previous_eod_by_security.get(security_id),
            cash_flows=cash_flows,
            has_portfolio_external_flow=self._has_external_flow(
                support_inputs.portfolio_cashflows_by_date.get(row.valuation_date, [])
            ),
        )
        ending_market_value_position = decimal_or_zero(row.eod_market_value)
        beginning_market_value_portfolio = (
            beginning_market_value_position * position_to_portfolio_rate
        )
        ending_market_value_portfolio = ending_market_value_position * position_to_portfolio_rate
        return PositionTimeseriesRow(
            position_id=f"{portfolio_id}:{security_id}",
            security_id=security_id,
            valuation_date=row.valuation_date,
            position_currency=position_currency,
            cash_flow_currency=position_currency,
            position_to_portfolio_fx_rate=position_to_portfolio_rate,
            portfolio_to_reporting_fx_rate=portfolio_to_reporting_rate,
            dimensions={dim: getattr(row, dim, None) for dim in dimensions},
            beginning_market_value_position_currency=beginning_market_value_position,
            ending_market_value_position_currency=ending_market_value_position,
            beginning_market_value_portfolio_currency=beginning_market_value_portfolio,
            ending_market_value_portfolio_currency=ending_market_value_portfolio,
            beginning_market_value_reporting_currency=(
                beginning_market_value_portfolio * portfolio_to_reporting_rate
            ),
            ending_market_value_reporting_currency=(
                ending_market_value_portfolio * portfolio_to_reporting_rate
            ),
            valuation_status=quality,
            quantity=decimal_or_zero(row.quantity),
            cash_flows=cash_flows,
        )

    @staticmethod
    def _position_to_portfolio_rate(
        *,
        position_currency: str,
        portfolio_currency: str,
        valuation_date: date,
        position_to_portfolio_rates: dict[str, dict[date, Decimal]],
    ) -> Decimal:
        if position_currency == portfolio_currency:
            return Decimal("1")
        rate_map = position_to_portfolio_rates.get(position_currency, {})
        if valuation_date not in rate_map:
            raise AnalyticsInputError(
                "INSUFFICIENT_DATA",
                "Missing FX rate for "
                f"{position_currency}/{portfolio_currency} on {valuation_date}.",
            )
        return rate_map[valuation_date]

    @staticmethod
    def _portfolio_to_reporting_rate(
        *,
        portfolio_currency: str,
        reporting_currency: str,
        valuation_date: date,
        fx_rates: dict[date, Decimal],
    ) -> Decimal:
        if reporting_currency == portfolio_currency:
            return Decimal("1")
        if valuation_date not in fx_rates:
            raise AnalyticsInputError(
                "INSUFFICIENT_DATA",
                "Missing FX rate for "
                f"{portfolio_currency}/{reporting_currency} on {valuation_date}.",
            )
        return fx_rates[valuation_date]

    async def get_portfolio_reference(
        self,
        *,
        portfolio_id: str,
        request: PortfolioAnalyticsReferenceRequest,
    ) -> PortfolioAnalyticsReferenceResponse:
        portfolio = await self.repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")
        latest_date = await self._latest_available_performance_date(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
        )
        fingerprint = self._request_fingerprint(
            {
                "endpoint": "portfolio-reference",
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
            }
        )
        performance_end_date = latest_date
        generated_at = datetime.now(UTC)
        return PortfolioAnalyticsReferenceResponse(
            portfolio_id=portfolio.portfolio_id,
            resolved_as_of_date=request.as_of_date,
            portfolio_currency=portfolio.base_currency,
            portfolio_open_date=portfolio.open_date,
            portfolio_close_date=portfolio.close_date,
            performance_end_date=performance_end_date,
            client_id=portfolio.client_id,
            booking_center_code=portfolio.booking_center_code,
            portfolio_type=portfolio.portfolio_type,
            objective=portfolio.objective,
            reference_state_policy="current_portfolio_reference_state",
            lineage=LineageMetadata(
                generated_by="integration.analytics_inputs",
                generated_at=generated_at,
                request_fingerprint=fingerprint,
                data_version="state_inputs_v1",
            ),
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=generated_at,
                data_quality_status=self._portfolio_reference_data_quality_status(
                    performance_end_date=performance_end_date,
                ),
                latest_evidence_timestamp=self._portfolio_reference_evidence_timestamp(portfolio),
            ),
        )

    @staticmethod
    def _timeseries_data_quality_status(
        *,
        required_count: int,
        observed_count: int,
        stale_count: int,
        warning_issue_count: int = 0,
    ) -> str:
        return classify_data_quality_coverage(
            DataQualityCoverageSignal(
                required_count=required_count,
                observed_count=observed_count,
                stale_count=stale_count,
                warning_issue_count=warning_issue_count,
            )
        )

    @staticmethod
    def _portfolio_reference_data_quality_status(*, performance_end_date: date | None) -> str:
        return COMPLETE if performance_end_date is not None else PARTIAL

    @staticmethod
    def _portfolio_reference_evidence_timestamp(portfolio: object) -> datetime | None:
        timestamps = [
            timestamp
            for field_name in ("source_timestamp", "updated_at", "created_at")
            if isinstance(timestamp := getattr(portfolio, field_name, None), datetime)
        ]
        return max(timestamps) if timestamps else None

    async def _latest_available_performance_date(
        self,
        *,
        portfolio_id: str,
        as_of_date: date,
        observed_dates: list[date] | None = None,
    ) -> date | None:
        latest_portfolio_date = await self.repo.get_latest_portfolio_timeseries_date(portfolio_id)
        latest_position_date = await self.repo.get_latest_position_timeseries_date(portfolio_id)
        latest_position_date = self._latest_position_horizon_with_observations(
            latest_position_date=latest_position_date,
            observed_dates=observed_dates,
        )
        return self._bounded_latest_performance_date(
            portfolio_candidate=self._latest_portfolio_horizon_candidate(
                latest_portfolio_date=latest_portfolio_date,
                observed_dates=observed_dates,
            ),
            latest_position_date=latest_position_date,
            as_of_date=as_of_date,
        )

    @staticmethod
    def _latest_position_horizon_with_observations(
        *,
        latest_position_date: date | None,
        observed_dates: list[date] | None,
    ) -> date | None:
        if not observed_dates:
            return latest_position_date
        observed_latest = max(observed_dates)
        return (
            observed_latest
            if latest_position_date is None
            else max(latest_position_date, observed_latest)
        )

    @staticmethod
    def _latest_portfolio_horizon_candidate(
        *,
        latest_portfolio_date: date | None,
        observed_dates: list[date] | None,
    ) -> date | None:
        portfolio_dates = [
            candidate for candidate in (latest_portfolio_date, *(observed_dates or [])) if candidate
        ]
        return max(portfolio_dates) if portfolio_dates else None

    @staticmethod
    def _bounded_latest_performance_date(
        *,
        portfolio_candidate: date | None,
        latest_position_date: date | None,
        as_of_date: date,
    ) -> date | None:
        horizon_candidates = AnalyticsTimeseriesService._performance_horizon_candidates(
            portfolio_candidate=portfolio_candidate,
            latest_position_date=latest_position_date,
        )
        if not horizon_candidates:
            return None
        return min(*horizon_candidates, as_of_date)

    @staticmethod
    def _performance_horizon_candidates(
        *,
        portfolio_candidate: date | None,
        latest_position_date: date | None,
    ) -> list[date]:
        return [
            candidate
            for candidate in (portfolio_candidate, latest_position_date)
            if candidate is not None
        ]

    @staticmethod
    def _export_result_endpoint(job_id: str) -> str:
        return f"/integration/exports/analytics-timeseries/jobs/{job_id}/result"

    @staticmethod
    def _normalize_export_job_status(status: str | None) -> str | None:
        if status is None:
            return None
        normalized_status = status.strip().lower()
        return normalized_status or None

    @classmethod
    def _to_export_response(
        cls, row: object, *, disposition: str = "status_lookup"
    ) -> AnalyticsExportJobResponse:
        normalized_status = cls._normalize_export_job_status(row.status)
        return AnalyticsExportJobResponse(
            job_id=row.job_id,
            dataset_type=row.dataset_type,
            portfolio_id=row.portfolio_id,
            status=normalized_status or row.status,
            disposition=disposition,
            lifecycle_mode=cls._EXPORT_LIFECYCLE_MODE,
            request_fingerprint=row.request_fingerprint,
            result_available=normalized_status == "completed",
            result_endpoint=cls._export_result_endpoint(row.job_id),
            result_format=row.result_format,
            compression=row.compression,
            result_row_count=row.result_row_count,
            error_message=row.error_message,
            created_at=row.created_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
        )

    @staticmethod
    def _jsonable(value: object) -> object:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, list):
            return [AnalyticsTimeseriesService._jsonable(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): AnalyticsTimeseriesService._jsonable(item) for key, item in value.items()
            }
        return value

    async def _reserve_export_job(
        self,
        *,
        request: AnalyticsExportCreateRequest,
        request_payload: dict,
        request_fingerprint: str,
    ) -> tuple[object, bool]:
        async with self.db.begin():
            existing = await self.export_repo.get_latest_by_fingerprint(
                request_fingerprint=request_fingerprint,
                dataset_type=request.dataset_type,
            )
            if existing is not None:
                existing_status = self._normalize_export_job_status(existing.status)
                if existing_status == "completed":
                    return existing, True
                if existing_status in {"accepted", "running"}:
                    stale_threshold = datetime.now(UTC) - timedelta(
                        minutes=self._analytics_export_stale_timeout_minutes
                    )
                    if existing.updated_at is not None and existing.updated_at >= stale_threshold:
                        return existing, True
                    await self.export_repo.mark_failed(
                        existing,
                        error_message=("Stale analytics export job superseded by a new request."),
                    )

            row = await self.export_repo.create_job(
                job_id=f"aexp_{uuid4().hex[:24]}",
                dataset_type=request.dataset_type,
                portfolio_id=request.portfolio_id,
                request_fingerprint=request_fingerprint,
                request_payload=request_payload,
                result_format=request.result_format,
                compression=request.compression,
            )
            return row, False

    async def _mark_export_job_running(self, job_id: str) -> object:
        async with self.db.begin():
            row = await self.export_repo.get_job(job_id)
            if row is None:
                raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
            await self.export_repo.mark_running(row)
            return row

    async def _mark_export_job_completed(
        self,
        job_id: str,
        *,
        result_payload: dict,
        result_row_count: int,
    ) -> object:
        async with self.db.begin():
            row = await self.export_repo.get_job(job_id)
            if row is None:
                raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
            await self.export_repo.mark_completed(
                row,
                result_payload=result_payload,
                result_row_count=result_row_count,
            )
            return row

    async def _mark_export_job_failed(self, job_id: str, *, error_message: str) -> object:
        async with self.db.begin():
            row = await self.export_repo.get_job(job_id)
            if row is None:
                raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
            await self.export_repo.mark_failed(row, error_message=error_message)
            return row

    async def create_export_job(
        self, request: AnalyticsExportCreateRequest
    ) -> AnalyticsExportJobResponse:
        request_payload = request.model_dump(mode="json")
        request_fingerprint = self._request_fingerprint(request_payload)
        row, reused = await self._reserve_export_job(
            request=request,
            request_payload=request_payload,
            request_fingerprint=request_fingerprint,
        )
        if reused:
            disposition = (
                "reused_completed"
                if self._normalize_export_job_status(row.status) == "completed"
                else "reused_inflight"
            )
            return self._to_export_response(row, disposition=disposition)

        job_id = row.job_id
        await self._mark_export_job_running(job_id)

        started = perf_counter()
        try:
            if request.dataset_type == "portfolio_timeseries":
                if request.portfolio_timeseries_request is None:
                    raise AnalyticsInputError(
                        "INVALID_REQUEST",
                        "portfolio_timeseries_request is required for "
                        "portfolio_timeseries exports.",
                    )
                data_rows, page_depth = await self._collect_portfolio_timeseries_for_export(
                    portfolio_id=request.portfolio_id,
                    request=request.portfolio_timeseries_request,
                )
            else:
                if request.position_timeseries_request is None:
                    raise AnalyticsInputError(
                        "INVALID_REQUEST",
                        "position_timeseries_request is required for position_timeseries exports.",
                    )
                data_rows, page_depth = await self._collect_position_timeseries_for_export(
                    portfolio_id=request.portfolio_id,
                    request=request.position_timeseries_request,
                )
            result_payload = {
                "job_id": job_id,
                "dataset_type": request.dataset_type,
                "request_fingerprint": request_fingerprint,
                "lifecycle_mode": self._EXPORT_LIFECYCLE_MODE,
                "generated_at": datetime.now(UTC).isoformat(),
                "contract_version": "rfc_063_v1",
                "result_row_count": len(data_rows),
                "data": self._jsonable(data_rows),
            }
            result_bytes = len(json.dumps(result_payload, separators=(",", ":")).encode("utf-8"))
            ANALYTICS_EXPORT_RESULT_BYTES.labels(
                request.result_format, request.compression
            ).observe(result_bytes)
            ANALYTICS_EXPORT_PAGE_DEPTH.labels(request.dataset_type).observe(page_depth)
            row = await self._mark_export_job_completed(
                job_id,
                result_payload=result_payload,
                result_row_count=len(data_rows),
            )
            ANALYTICS_EXPORT_JOBS_TOTAL.labels(request.dataset_type, "completed").inc()
            return self._to_export_response(row, disposition="created")
        except AnalyticsInputError as exc:
            row = await self._mark_export_job_failed(job_id, error_message=str(exc))
            ANALYTICS_EXPORT_JOBS_TOTAL.labels(request.dataset_type, "failed").inc()
            return self._to_export_response(row, disposition="created")
        except Exception:
            logger.exception(
                "Analytics export job %s failed unexpectedly for dataset %s",
                job_id,
                request.dataset_type,
            )
            await self._mark_export_job_failed(
                job_id,
                error_message="Unexpected analytics export processing failure.",
            )
            ANALYTICS_EXPORT_JOBS_TOTAL.labels(request.dataset_type, "failed").inc()
            raise
        finally:
            ANALYTICS_EXPORT_JOB_DURATION_SECONDS.labels(request.dataset_type).observe(
                perf_counter() - started
            )

    async def get_export_job(self, job_id: str) -> AnalyticsExportJobResponse:
        row = await self.export_repo.get_job(job_id)
        if row is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
        return self._to_export_response(row)

    async def get_export_result_json(self, job_id: str) -> AnalyticsExportJsonResultResponse:
        row = await self.export_repo.get_job(job_id)
        if row is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
        if self._normalize_export_job_status(row.status) != "completed":
            raise AnalyticsInputError(
                "UNSUPPORTED_CONFIGURATION",
                "Export job is not completed yet; result unavailable.",
            )
        if not isinstance(row.result_payload, dict):
            raise AnalyticsInputError("INSUFFICIENT_DATA", "Export job completed without payload.")
        return AnalyticsExportJsonResultResponse(**row.result_payload)

    async def get_export_result_ndjson(
        self, job_id: str, *, compression: str
    ) -> tuple[bytes, str, str]:
        row = await self.export_repo.get_job(job_id)
        if row is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
        if self._normalize_export_job_status(row.status) != "completed":
            raise AnalyticsInputError(
                "UNSUPPORTED_CONFIGURATION",
                "Export job is not completed yet; result unavailable.",
            )
        if not isinstance(row.result_payload, dict):
            raise AnalyticsInputError("INSUFFICIENT_DATA", "Export job completed without payload.")
        payload_data = row.result_payload.get("data")
        if not isinstance(payload_data, list):
            raise AnalyticsInputError("INSUFFICIENT_DATA", "Export payload data is malformed.")

        header = {
            "record_type": "metadata",
            "job_id": row.job_id,
            "dataset_type": row.dataset_type,
            "generated_at": row.result_payload.get("generated_at"),
            "contract_version": row.result_payload.get("contract_version"),
        }
        lines = [json.dumps(header, separators=(",", ":"))]
        for item in payload_data:
            lines.append(json.dumps({"record_type": "data", "record": item}, separators=(",", ":")))
        encoded = ("\n".join(lines) + "\n").encode("utf-8")
        content_encoding = "none"
        if compression == "gzip":
            encoded = gzip.compress(encoded)
            content_encoding = "gzip"
        return (encoded, "application/x-ndjson", content_encoding)

    async def _collect_portfolio_timeseries_for_export(
        self, *, portfolio_id: str, request: PortfolioAnalyticsTimeseriesRequest
    ) -> tuple[list[dict[str, object]], int]:
        rows: list[dict[str, object]] = []
        page_depth = 0
        page_token: str | None = None
        while True:
            page_depth += 1
            page_request = request.page.model_copy(
                update={"page_token": page_token, "page_size": 2000}
            )
            paged_request = request.model_copy(update={"page": page_request})
            response = await self.get_portfolio_timeseries(
                portfolio_id=portfolio_id,
                request=paged_request,
            )
            rows.extend([item.model_dump(mode="json") for item in response.observations])
            page_token = response.page.next_page_token
            if not page_token:
                break
        return rows, page_depth

    async def _collect_position_timeseries_for_export(
        self, *, portfolio_id: str, request: PositionAnalyticsTimeseriesRequest
    ) -> tuple[list[dict[str, object]], int]:
        rows: list[dict[str, object]] = []
        page_depth = 0
        page_token: str | None = None
        while True:
            page_depth += 1
            page_request = request.page.model_copy(
                update={"page_token": page_token, "page_size": 2000}
            )
            paged_request = request.model_copy(update={"page": page_request})
            response = await self.get_position_timeseries(
                portfolio_id=portfolio_id,
                request=paged_request,
            )
            rows.extend([item.model_dump(mode="json") for item in response.rows])
            page_token = response.page.next_page_token
            if not page_token:
                break
        return rows, page_depth
