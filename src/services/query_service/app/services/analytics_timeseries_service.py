from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

from portfolio_common.monitoring import (
    ANALYTICS_EXPORT_JOB_DURATION_SECONDS,
    ANALYTICS_EXPORT_JOBS_TOTAL,
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
from .analytics_cash_flows import (
    AnalyticsCashFlowError,
    build_cash_flow_observation,
    effective_beginning_market_value,
    has_external_flow,
    portfolio_cash_flows_for_dates,
    position_cash_flows_for_keys,
)
from .analytics_export_jobs import (
    analytics_export_job_response,
    analytics_export_result_payload,
    normalize_analytics_export_job_status,
    record_analytics_export_result_metrics,
    reused_analytics_export_job_response,
)
from .analytics_export_ndjson import AnalyticsExportNdjsonError, analytics_export_ndjson_result
from .analytics_fx_rates import (
    AnalyticsFxRateError,
    get_portfolio_to_reporting_rates,
    get_position_to_portfolio_rate_maps,
    portfolio_to_reporting_rate,
    position_to_portfolio_rate,
)
from .analytics_page_tokens import (
    AnalyticsPageTokenError,
    AnalyticsPageTokenSignatureError,
    decode_analytics_page_token,
    encode_analytics_page_token,
)
from .analytics_pagination import (
    AnalyticsPaginationError,
    PositionTimeseriesCursor,
    portfolio_timeseries_cursor_date,
    portfolio_timeseries_diagnostics,
    portfolio_timeseries_scope_fingerprint,
    position_timeseries_cursor,
    position_timeseries_diagnostics,
    position_timeseries_next_page_token,
    position_timeseries_scope_fingerprint,
)
from .analytics_quality import (
    bounded_latest_performance_date,
    latest_portfolio_horizon_candidate,
    latest_position_horizon_with_observations,
    performance_horizon_candidates,
    portfolio_reference_data_quality_status,
    portfolio_reference_evidence_timestamp,
    quality_status_from_epoch,
    timeseries_data_quality_status,
)
from .analytics_windows import AnalyticsWindowError, resolve_analytics_window
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
        return encode_analytics_page_token(payload=payload, secret=self._page_token_secret)

    def _decode_page_token(self, token: str | None) -> dict:
        try:
            return decode_analytics_page_token(token=token, secret=self._page_token_secret)
        except AnalyticsPageTokenSignatureError as exc:
            raise AnalyticsInputError("INVALID_REQUEST", str(exc)) from exc
        except AnalyticsPageTokenError as exc:
            raise AnalyticsInputError("INVALID_REQUEST", "Malformed page token.") from exc

    def _resolve_window(
        self,
        *,
        as_of_date: date,
        window: AnalyticsWindow | None,
        period: str | None,
        inception_date: date,
    ) -> AnalyticsWindow:
        try:
            return resolve_analytics_window(
                as_of_date=as_of_date,
                window=window,
                period=period,
                inception_date=inception_date,
            )
        except AnalyticsWindowError as exc:
            raise AnalyticsInputError("INVALID_REQUEST", str(exc)) from exc

    async def _get_conversion_rates(
        self,
        *,
        portfolio_currency: str,
        reporting_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        return await get_portfolio_to_reporting_rates(
            self.repo,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
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
        return await get_position_to_portfolio_rate_maps(
            self.repo,
            position_currencies=position_currencies,
            portfolio_currency=portfolio_currency,
            start_date=start_date,
            end_date=end_date,
        )

    @staticmethod
    def _quality_status_from_epoch(epoch: int) -> str:
        return quality_status_from_epoch(epoch)

    @staticmethod
    def _build_cash_flow_observation(
        row: object,
        *,
        amount: Decimal,
    ) -> CashFlowObservation:
        return build_cash_flow_observation(row, amount=amount)

    def _portfolio_cash_flows_for_dates(
        self,
        cashflow_rows: list[object],
        *,
        reporting_currency: str,
        portfolio_currency: str,
        fx_rates: dict[date, Decimal],
    ) -> dict[date, list[CashFlowObservation]]:
        try:
            return portfolio_cash_flows_for_dates(
                cashflow_rows,
                reporting_currency=reporting_currency,
                portfolio_currency=portfolio_currency,
                fx_rates=fx_rates,
            )
        except AnalyticsCashFlowError as exc:
            raise AnalyticsInputError("INSUFFICIENT_DATA", str(exc)) from exc

    def _position_cash_flows_for_keys(
        self,
        cashflow_rows: list[object],
    ) -> dict[tuple[str, date], list[CashFlowObservation]]:
        return position_cash_flows_for_keys(cashflow_rows)

    @staticmethod
    def _has_external_flow(cash_flows: list[CashFlowObservation]) -> bool:
        return has_external_flow(cash_flows)

    @staticmethod
    def _effective_beginning_market_value(
        row: object,
        *,
        previous_eod_market_value: Decimal | None,
        cash_flows: list[CashFlowObservation],
        has_portfolio_external_flow: bool,
    ) -> Decimal:
        return effective_beginning_market_value(
            row,
            previous_eod_market_value=previous_eod_market_value,
            cash_flows=cash_flows,
            has_portfolio_external_flow=has_portfolio_external_flow,
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
        return portfolio_timeseries_scope_fingerprint(
            portfolio_id=portfolio_id,
            request=request,
            resolved_window=resolved_window,
            reporting_currency=reporting_currency,
        )

    def _portfolio_timeseries_cursor_date(
        self,
        *,
        page_token: str | None,
        request_scope_fingerprint: str,
    ) -> date | None:
        try:
            return portfolio_timeseries_cursor_date(
                page_token=page_token,
                request_scope_fingerprint=request_scope_fingerprint,
                decode_page_token=self._decode_page_token,
            )
        except AnalyticsPaginationError as exc:
            raise AnalyticsInputError("INVALID_REQUEST", str(exc)) from exc

    @staticmethod
    def _portfolio_timeseries_diagnostics(
        *,
        quality_distribution: dict[str, int],
        expected_business_dates: list[date],
        observed_dates: list[date],
    ) -> PortfolioQualityDiagnostics:
        return portfolio_timeseries_diagnostics(
            quality_distribution=quality_distribution,
            expected_business_dates=expected_business_dates,
            observed_dates=observed_dates,
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
        request_scope_fingerprint = self._position_timeseries_scope_fingerprint(
            portfolio_id=portfolio_id,
            request=request,
            resolved_window=resolved_window,
            reporting_currency=reporting_currency,
        )
        cursor = self._position_timeseries_cursor(
            page_token=request.page.page_token,
            request_scope_fingerprint=request_scope_fingerprint,
        )
        dimension_filters = self._position_dimension_filters(request)
        snapshot_epoch = await self._position_snapshot_epoch(
            portfolio_id=portfolio_id,
            request=request,
            resolved_window=resolved_window,
            dimension_filters=dimension_filters,
            cursor=cursor,
        )
        rows = await self.repo.list_position_timeseries_rows(
            portfolio_id=portfolio_id,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
            page_size=request.page.page_size,
            cursor_date=cursor.cursor_date,
            cursor_security_id=cursor.cursor_security_id,
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

        next_page_token = self._position_timeseries_next_page_token(
            has_more=has_more,
            rows_page=rows_page,
            snapshot_epoch=snapshot_epoch,
            request_scope_fingerprint=request_scope_fingerprint,
        )
        diagnostics = self._position_timeseries_diagnostics(
            quality_distribution=quality_distribution,
            dimensions=request.dimensions,
            include_cash_flows=request.include_cash_flows,
        )
        data_quality_status = self._timeseries_data_quality_status(
            required_count=len(response_rows),
            observed_count=len(response_rows),
            stale_count=diagnostics.stale_points_count,
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
            diagnostics=diagnostics,
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

    def _position_timeseries_scope_fingerprint(
        self,
        *,
        portfolio_id: str,
        request: PositionAnalyticsTimeseriesRequest,
        resolved_window: AnalyticsWindow,
        reporting_currency: str,
    ) -> str:
        return position_timeseries_scope_fingerprint(
            portfolio_id=portfolio_id,
            request=request,
            resolved_window=resolved_window,
            reporting_currency=reporting_currency,
        )

    def _position_timeseries_cursor(
        self,
        *,
        page_token: str | None,
        request_scope_fingerprint: str,
    ) -> PositionTimeseriesCursor:
        try:
            return position_timeseries_cursor(
                page_token=page_token,
                request_scope_fingerprint=request_scope_fingerprint,
                decode_page_token=self._decode_page_token,
            )
        except AnalyticsPaginationError as exc:
            raise AnalyticsInputError("INVALID_REQUEST", str(exc)) from exc

    @staticmethod
    def _position_dimension_filters(
        request: PositionAnalyticsTimeseriesRequest,
    ) -> dict[str, set[str]]:
        return {item.dimension: set(item.values) for item in request.filters.dimension_filters}

    async def _position_snapshot_epoch(
        self,
        *,
        portfolio_id: str,
        request: PositionAnalyticsTimeseriesRequest,
        resolved_window: AnalyticsWindow,
        dimension_filters: dict[str, set[str]],
        cursor: PositionTimeseriesCursor,
    ) -> int:
        if cursor.snapshot_epoch is not None:
            return cursor.snapshot_epoch
        return await self.repo.get_position_snapshot_epoch(
            portfolio_id=portfolio_id,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
            security_ids=request.filters.security_ids,
            position_ids=request.filters.position_ids,
            dimension_filters=dimension_filters,
        )

    def _position_timeseries_next_page_token(
        self,
        *,
        has_more: bool,
        rows_page: list[object],
        snapshot_epoch: int,
        request_scope_fingerprint: str,
    ) -> str | None:
        return position_timeseries_next_page_token(
            has_more=has_more,
            rows_page=rows_page,
            snapshot_epoch=snapshot_epoch,
            request_scope_fingerprint=request_scope_fingerprint,
            encode_page_token=self._encode_page_token,
        )

    @staticmethod
    def _position_timeseries_diagnostics(
        *,
        quality_distribution: dict[str, int],
        dimensions: list[str],
        include_cash_flows: bool,
    ) -> QualityDiagnostics:
        return position_timeseries_diagnostics(
            quality_distribution=quality_distribution,
            dimensions=dimensions,
            include_cash_flows=include_cash_flows,
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
        try:
            return position_to_portfolio_rate(
                position_currency=position_currency,
                portfolio_currency=portfolio_currency,
                valuation_date=valuation_date,
                position_to_portfolio_rates=position_to_portfolio_rates,
            )
        except AnalyticsFxRateError as exc:
            raise AnalyticsInputError("INSUFFICIENT_DATA", str(exc)) from exc

    @staticmethod
    def _portfolio_to_reporting_rate(
        *,
        portfolio_currency: str,
        reporting_currency: str,
        valuation_date: date,
        fx_rates: dict[date, Decimal],
    ) -> Decimal:
        try:
            return portfolio_to_reporting_rate(
                portfolio_currency=portfolio_currency,
                reporting_currency=reporting_currency,
                valuation_date=valuation_date,
                fx_rates=fx_rates,
            )
        except AnalyticsFxRateError as exc:
            raise AnalyticsInputError("INSUFFICIENT_DATA", str(exc)) from exc

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
        return timeseries_data_quality_status(
            required_count=required_count,
            observed_count=observed_count,
            stale_count=stale_count,
            warning_issue_count=warning_issue_count,
        )

    @staticmethod
    def _portfolio_reference_data_quality_status(*, performance_end_date: date | None) -> str:
        return portfolio_reference_data_quality_status(performance_end_date=performance_end_date)

    @staticmethod
    def _portfolio_reference_evidence_timestamp(portfolio: object) -> datetime | None:
        return portfolio_reference_evidence_timestamp(portfolio)

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
        return latest_position_horizon_with_observations(
            latest_position_date=latest_position_date,
            observed_dates=observed_dates,
        )

    @staticmethod
    def _latest_portfolio_horizon_candidate(
        *,
        latest_portfolio_date: date | None,
        observed_dates: list[date] | None,
    ) -> date | None:
        return latest_portfolio_horizon_candidate(
            latest_portfolio_date=latest_portfolio_date,
            observed_dates=observed_dates,
        )

    @staticmethod
    def _bounded_latest_performance_date(
        *,
        portfolio_candidate: date | None,
        latest_position_date: date | None,
        as_of_date: date,
    ) -> date | None:
        return bounded_latest_performance_date(
            portfolio_candidate=portfolio_candidate,
            latest_position_date=latest_position_date,
            as_of_date=as_of_date,
        )

    @staticmethod
    def _performance_horizon_candidates(
        *,
        portfolio_candidate: date | None,
        latest_position_date: date | None,
    ) -> list[date]:
        return performance_horizon_candidates(
            portfolio_candidate=portfolio_candidate,
            latest_position_date=latest_position_date,
        )

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
                if self._export_job_is_completed(existing):
                    return existing, True
                if self._export_job_is_inflight(existing):
                    if self._export_job_is_fresh(existing):
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

    def _export_job_is_completed(self, row: object) -> bool:
        return normalize_analytics_export_job_status(row.status) == "completed"

    def _export_job_is_inflight(self, row: object) -> bool:
        return normalize_analytics_export_job_status(row.status) in {"accepted", "running"}

    def _export_job_is_fresh(self, row: object) -> bool:
        return row.updated_at is not None and row.updated_at >= self._export_job_stale_threshold()

    def _export_job_stale_threshold(self) -> datetime:
        return datetime.now(UTC) - timedelta(minutes=self._analytics_export_stale_timeout_minutes)

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
            return reused_analytics_export_job_response(
                row, lifecycle_mode=self._EXPORT_LIFECYCLE_MODE
            )

        job_id = row.job_id
        await self._mark_export_job_running(job_id)

        started = perf_counter()
        try:
            data_rows, page_depth = await self._collect_export_dataset(request)
            row = await self._complete_export_job_with_result(
                job_id=job_id,
                request=request,
                request_fingerprint=request_fingerprint,
                data_rows=data_rows,
                page_depth=page_depth,
            )
            ANALYTICS_EXPORT_JOBS_TOTAL.labels(request.dataset_type, "completed").inc()
            return analytics_export_job_response(
                row,
                lifecycle_mode=self._EXPORT_LIFECYCLE_MODE,
                disposition="created",
            )
        except AnalyticsInputError as exc:
            row = await self._mark_export_job_failed(job_id, error_message=str(exc))
            ANALYTICS_EXPORT_JOBS_TOTAL.labels(request.dataset_type, "failed").inc()
            return analytics_export_job_response(
                row,
                lifecycle_mode=self._EXPORT_LIFECYCLE_MODE,
                disposition="created",
            )
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

    async def _collect_export_dataset(
        self, request: AnalyticsExportCreateRequest
    ) -> tuple[list[dict[str, object]], int]:
        if request.dataset_type == "portfolio_timeseries":
            if request.portfolio_timeseries_request is None:
                raise AnalyticsInputError(
                    "INVALID_REQUEST",
                    "portfolio_timeseries_request is required for portfolio_timeseries exports.",
                )
            return await self._collect_portfolio_timeseries_for_export(
                portfolio_id=request.portfolio_id,
                request=request.portfolio_timeseries_request,
            )
        if request.position_timeseries_request is None:
            raise AnalyticsInputError(
                "INVALID_REQUEST",
                "position_timeseries_request is required for position_timeseries exports.",
            )
        return await self._collect_position_timeseries_for_export(
            portfolio_id=request.portfolio_id,
            request=request.position_timeseries_request,
        )

    async def _complete_export_job_with_result(
        self,
        *,
        job_id: str,
        request: AnalyticsExportCreateRequest,
        request_fingerprint: str,
        data_rows: list[dict[str, object]],
        page_depth: int,
    ) -> object:
        result_payload = analytics_export_result_payload(
            job_id=job_id,
            dataset_type=request.dataset_type,
            request_fingerprint=request_fingerprint,
            lifecycle_mode=self._EXPORT_LIFECYCLE_MODE,
            data_rows=data_rows,
        )
        record_analytics_export_result_metrics(
            result_format=request.result_format,
            compression=request.compression,
            dataset_type=request.dataset_type,
            result_payload=result_payload,
            page_depth=page_depth,
        )
        return await self._mark_export_job_completed(
            job_id,
            result_payload=result_payload,
            result_row_count=len(data_rows),
        )

    async def get_export_job(self, job_id: str) -> AnalyticsExportJobResponse:
        row = await self.export_repo.get_job(job_id)
        if row is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
        return analytics_export_job_response(row, lifecycle_mode=self._EXPORT_LIFECYCLE_MODE)

    async def get_export_result_json(self, job_id: str) -> AnalyticsExportJsonResultResponse:
        row = await self.export_repo.get_job(job_id)
        if row is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
        if normalize_analytics_export_job_status(row.status) != "completed":
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
        if normalize_analytics_export_job_status(row.status) != "completed":
            raise AnalyticsInputError(
                "UNSUPPORTED_CONFIGURATION",
                "Export job is not completed yet; result unavailable.",
            )
        if not isinstance(row.result_payload, dict):
            raise AnalyticsInputError("INSUFFICIENT_DATA", "Export job completed without payload.")
        try:
            result = analytics_export_ndjson_result(
                job_id=row.job_id,
                dataset_type=row.dataset_type,
                result_payload=row.result_payload,
                compression=compression,
            )
        except AnalyticsExportNdjsonError as exc:
            raise AnalyticsInputError("INSUFFICIENT_DATA", str(exc)) from exc
        return (result.content, result.media_type, result.content_encoding)

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
