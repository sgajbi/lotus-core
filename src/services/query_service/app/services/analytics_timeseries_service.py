from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

from portfolio_common.monitoring import (
    ANALYTICS_EXPORT_JOB_DURATION_SECONDS,
    ANALYTICS_EXPORT_JOBS_TOTAL,
    ANALYTICS_EXPORT_PAGE_DEPTH,
    ANALYTICS_EXPORT_RESULT_BYTES,
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
from ..repositories.analytics_export_repository import AnalyticsExportRepository
from ..repositories.analytics_timeseries_repository import AnalyticsTimeseriesRepository
from ..settings import load_query_service_settings


class AnalyticsInputError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


logger = logging.getLogger(__name__)


class AnalyticsTimeseriesService:
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
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.md5(serialized.encode("utf-8")).hexdigest()  # nosec B324

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
            end_date = min(window.end_date, as_of_date)
            if window.start_date > end_date:
                raise AnalyticsInputError(
                    "INVALID_REQUEST", "window.start_date must be before or equal to end_date."
                )
            return AnalyticsWindow(start_date=window.start_date, end_date=end_date)

        if period == "one_month":
            start = as_of_date - timedelta(days=31)
        elif period == "three_months":
            start = as_of_date - timedelta(days=92)
        elif period == "ytd":
            start = date(as_of_date.year, 1, 1)
        elif period == "one_year":
            start = as_of_date - timedelta(days=365)
        elif period == "three_years":
            start = as_of_date - timedelta(days=365 * 3)
        elif period == "five_years":
            start = as_of_date - timedelta(days=365 * 5)
        elif period == "inception":
            start = inception_date
        else:
            raise AnalyticsInputError("INVALID_REQUEST", "Unsupported period value.")

        if start < inception_date:
            start = inception_date
        return AnalyticsWindow(start_date=start, end_date=as_of_date)

    async def _get_conversion_rates(
        self,
        *,
        portfolio_currency: str,
        reporting_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        if portfolio_currency == reporting_currency:
            return {}
        return await self.repo.get_fx_rates_map(
            from_currency=portfolio_currency,
            to_currency=reporting_currency,
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
        rates: dict[str, dict[date, Decimal]] = {}
        for position_currency in sorted(position_currencies):
            if not position_currency or position_currency == portfolio_currency:
                rates[position_currency] = {}
                continue
            rates[position_currency] = await self.repo.get_fx_rates_map(
                from_currency=position_currency,
                to_currency=portfolio_currency,
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
    def _cash_flows_from_portfolio_row(row: object) -> list[CashFlowObservation]:
        flows: list[CashFlowObservation] = []
        bod = Decimal(row.bod_cashflow)
        eod = Decimal(row.eod_cashflow)
        fees = Decimal(row.fees)
        if bod != 0:
            flows.append(
                CashFlowObservation(amount=bod, timing="bod", cash_flow_type="external_flow")
            )
        if eod != 0:
            flows.append(
                CashFlowObservation(amount=eod, timing="eod", cash_flow_type="external_flow")
            )
        if fees != 0:
            flows.append(CashFlowObservation(amount=fees, timing="eod", cash_flow_type="fee"))
        return flows

    async def get_portfolio_timeseries(
        self,
        *,
        portfolio_id: str,
        request: PortfolioAnalyticsTimeseriesRequest,
    ) -> PortfolioAnalyticsTimeseriesResponse:
        portfolio = await self.repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")

        resolved_window = self._resolve_window(
            as_of_date=request.as_of_date,
            window=request.window,
            period=request.period,
            inception_date=portfolio.open_date,
        )
        reporting_currency = request.reporting_currency or portfolio.base_currency
        request_scope_fingerprint = self._request_fingerprint(
            {
                "endpoint": "portfolio-timeseries",
                "portfolio_id": portfolio_id,
                "as_of_date": request.as_of_date.isoformat(),
                "resolved_window": resolved_window.model_dump(mode="json"),
                "frequency": request.frequency,
                "reporting_currency": reporting_currency,
            }
        )
        fx_rates = await self._get_conversion_rates(
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
        )

        cursor = self._decode_page_token(request.page.page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope is not None and token_scope != request_scope_fingerprint:
            raise AnalyticsInputError("INVALID_REQUEST", "Page token does not match request scope.")
        cursor_date = (
            date.fromisoformat(cursor["valuation_date"]) if cursor.get("valuation_date") else None
        )
        snapshot_epoch = int(cursor["snapshot_epoch"]) if cursor.get("snapshot_epoch") else None
        if snapshot_epoch is None:
            if hasattr(self.repo, "get_portfolio_snapshot_epoch"):
                snapshot_epoch = await self.repo.get_portfolio_snapshot_epoch(
                    portfolio_id=portfolio_id,
                    start_date=resolved_window.start_date,
                    end_date=resolved_window.end_date,
                )
            else:
                snapshot_epoch = 0
        rows = await self.repo.list_portfolio_timeseries_rows(
            portfolio_id=portfolio_id,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
            page_size=request.page.page_size,
            cursor_date=cursor_date,
            snapshot_epoch=snapshot_epoch,
        )
        expected_business_dates = await self.repo.list_business_dates(
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
        )
        observed_dates = await self.repo.list_portfolio_observation_dates(
            portfolio_id=portfolio_id,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
            snapshot_epoch=snapshot_epoch,
        )

        has_more = len(rows) > request.page.page_size
        rows_page = rows[: request.page.page_size]

        observations: list[PortfolioTimeseriesObservation] = []
        quality_distribution: dict[str, int] = {}
        for row in rows_page:
            valuation_date = row.valuation_date
            conversion_rate = Decimal("1")
            if reporting_currency != portfolio.base_currency:
                if valuation_date not in fx_rates:
                    raise AnalyticsInputError(
                        "INSUFFICIENT_DATA",
                        "Missing FX rate for "
                        f"{portfolio.base_currency}/{reporting_currency} on {valuation_date}.",
                    )
                conversion_rate = fx_rates[valuation_date]
            quality = self._quality_status_from_epoch(int(row.epoch))
            quality_distribution[quality] = quality_distribution.get(quality, 0) + 1

            observations.append(
                PortfolioTimeseriesObservation(
                    valuation_date=valuation_date,
                    beginning_market_value=Decimal(row.bod_market_value) * conversion_rate,
                    ending_market_value=Decimal(row.eod_market_value) * conversion_rate,
                    valuation_status=quality,
                    cash_flows=[
                        CashFlowObservation(
                            amount=flow.amount * conversion_rate,
                            timing=flow.timing,
                            cash_flow_type=flow.cash_flow_type,
                        )
                        for flow in self._cash_flows_from_portfolio_row(row)
                    ],
                    cash_flow_currency=reporting_currency,
                )
            )

        next_page_token: str | None = None
        if has_more and rows_page:
            next_page_token = self._encode_page_token(
                {
                    "valuation_date": rows_page[-1].valuation_date.isoformat(),
                    "snapshot_epoch": snapshot_epoch,
                    "scope_fingerprint": request_scope_fingerprint,
                }
            )

        latest_date = await self.repo.get_latest_portfolio_timeseries_date(portfolio_id)
        missing_dates = sorted(set(expected_business_dates) - set(observed_dates))
        stale_points_count = sum(
            count for status_name, count in quality_distribution.items() if status_name != "final"
        )
        fingerprint = self._request_fingerprint(
            {
                "endpoint": "portfolio-timeseries",
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
            }
        )
        return PortfolioAnalyticsTimeseriesResponse(
            portfolio_id=portfolio_id,
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            portfolio_open_date=portfolio.open_date,
            portfolio_close_date=portfolio.close_date,
            performance_end_date=latest_date,
            resolved_window=resolved_window,
            frequency=request.frequency,
            lineage=LineageMetadata(
                generated_by="integration.analytics_inputs",
                generated_at=datetime.now(UTC),
                request_fingerprint=fingerprint,
                data_version="state_inputs_v1",
            ),
            diagnostics=PortfolioQualityDiagnostics(
                quality_status_distribution=quality_distribution,
                missing_dates_count=len(missing_dates),
                stale_points_count=stale_points_count,
                expected_business_dates_count=len(expected_business_dates),
                returned_observation_dates_count=len(observed_dates),
                cash_flows_included=True,
            ),
            page=PageMetadata(
                page_size=request.page.page_size,
                returned_row_count=len(observations),
                sort_key="valuation_date:asc",
                request_scope_fingerprint=request_scope_fingerprint,
                snapshot_epoch=snapshot_epoch,
                next_page_token=next_page_token,
            ),
            observations=observations,
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
        resolved_window = self._resolve_window(
            as_of_date=request.as_of_date,
            window=request.window,
            period=request.period,
            inception_date=portfolio.open_date,
        )
        reporting_currency = request.reporting_currency or portfolio.base_currency
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
        fx_rates = await self._get_conversion_rates(
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
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
            if hasattr(self.repo, "get_position_snapshot_epoch"):
                snapshot_epoch = await self.repo.get_position_snapshot_epoch(
                    portfolio_id=portfolio_id,
                    start_date=resolved_window.start_date,
                    end_date=resolved_window.end_date,
                    security_ids=request.filters.security_ids,
                    position_ids=request.filters.position_ids,
                    dimension_filters=dimension_filters,
                )
            else:
                snapshot_epoch = 0
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
        position_to_portfolio_rates = await self._get_position_to_portfolio_rate_maps(
            position_currencies={str(row.position_currency or "") for row in rows},
            portfolio_currency=portfolio.base_currency,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
        )

        has_more = len(rows) > request.page.page_size
        rows_page = rows[: request.page.page_size]

        quality_distribution: dict[str, int] = {}
        response_rows: list[PositionTimeseriesRow] = []
        for row in rows_page:
            quality = self._quality_status_from_epoch(int(row.epoch))
            quality_distribution[quality] = quality_distribution.get(quality, 0) + 1
            position_currency = row.position_currency or portfolio.base_currency
            position_to_portfolio_rate = Decimal("1")
            if position_currency != portfolio.base_currency:
                rate_map = position_to_portfolio_rates.get(position_currency, {})
                if row.valuation_date not in rate_map:
                    raise AnalyticsInputError(
                        "INSUFFICIENT_DATA",
                        "Missing FX rate for "
                        f"{position_currency}/{portfolio.base_currency} on {row.valuation_date}.",
                    )
                position_to_portfolio_rate = rate_map[row.valuation_date]

            portfolio_to_reporting_rate = Decimal("1")
            if reporting_currency != portfolio.base_currency:
                if row.valuation_date not in fx_rates:
                    raise AnalyticsInputError(
                        "INSUFFICIENT_DATA",
                        "Missing FX rate for "
                        f"{portfolio.base_currency}/{reporting_currency} on {row.valuation_date}.",
                    )
                portfolio_to_reporting_rate = fx_rates[row.valuation_date]

            beginning_market_value_position = Decimal(row.bod_market_value)
            ending_market_value_position = Decimal(row.eod_market_value)
            beginning_market_value_portfolio = (
                beginning_market_value_position * position_to_portfolio_rate
            )
            ending_market_value_portfolio = (
                ending_market_value_position * position_to_portfolio_rate
            )

            position_id = f"{portfolio_id}:{row.security_id}"
            dimensions = {dim: getattr(row, dim, None) for dim in request.dimensions}
            cash_flows: list[CashFlowObservation] = []
            if request.include_cash_flows:
                bod = Decimal(row.bod_cashflow_position)
                eod = Decimal(row.eod_cashflow_position)
                fees = Decimal(row.fees)
                if bod != 0:
                    cash_flows.append(
                        CashFlowObservation(
                            amount=bod,
                            timing="bod",
                            cash_flow_type="external_flow",
                        )
                    )
                if eod != 0:
                    cash_flows.append(
                        CashFlowObservation(
                            amount=eod,
                            timing="eod",
                            cash_flow_type="external_flow",
                        )
                    )
                if fees != 0:
                    cash_flows.append(
                        CashFlowObservation(amount=fees, timing="eod", cash_flow_type="fee")
                    )

            response_rows.append(
                    PositionTimeseriesRow(
                        position_id=position_id,
                        security_id=row.security_id,
                        valuation_date=row.valuation_date,
                        position_currency=row.position_currency,
                        cash_flow_currency=position_currency,
                        position_to_portfolio_fx_rate=position_to_portfolio_rate,
                        portfolio_to_reporting_fx_rate=portfolio_to_reporting_rate,
                        dimensions=dimensions,
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
                        quantity=Decimal(row.quantity),
                        cash_flows=cash_flows,
                )
            )

        next_page_token: str | None = None
        if has_more and rows_page:
            last = rows_page[-1]
            next_page_token = self._encode_page_token(
                {
                    "valuation_date": last.valuation_date.isoformat(),
                    "security_id": last.security_id,
                    "snapshot_epoch": snapshot_epoch,
                    "scope_fingerprint": request_scope_fingerprint,
                }
            )

        fingerprint = self._request_fingerprint(
            {
                "endpoint": "position-timeseries",
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
            }
        )
        return PositionAnalyticsTimeseriesResponse(
            portfolio_id=portfolio_id,
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            resolved_window=resolved_window,
            frequency=request.frequency,
            lineage=LineageMetadata(
                generated_by="integration.analytics_inputs",
                generated_at=datetime.now(UTC),
                request_fingerprint=fingerprint,
                data_version="state_inputs_v1",
            ),
            diagnostics=QualityDiagnostics(
                quality_status_distribution=quality_distribution,
                missing_dates_count=0,
                stale_points_count=0,
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
        )

    async def get_portfolio_reference(
        self,
        *,
        portfolio_id: str,
        request: PortfolioAnalyticsReferenceRequest,
    ) -> PortfolioAnalyticsReferenceResponse:
        portfolio = await self.repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")
        latest_date = await self.repo.get_latest_portfolio_timeseries_date(portfolio_id)
        fingerprint = self._request_fingerprint(
            {
                "endpoint": "portfolio-reference",
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
            }
        )
        performance_end_date = (
            min(latest_date, request.as_of_date) if latest_date is not None else None
        )
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
                generated_at=datetime.now(UTC),
                request_fingerprint=fingerprint,
                data_version="state_inputs_v1",
            ),
        )

    @staticmethod
    def _to_export_response(row: object) -> AnalyticsExportJobResponse:
        return AnalyticsExportJobResponse(
            job_id=row.job_id,
            dataset_type=row.dataset_type,
            portfolio_id=row.portfolio_id,
            status=row.status,
            request_fingerprint=row.request_fingerprint,
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
                if existing.status == "completed":
                    return existing, True
                if existing.status in {"accepted", "running"}:
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
            return self._to_export_response(row)

        job_id = row.job_id
        await self._mark_export_job_running(job_id)

        started = perf_counter()
        try:
            if request.dataset_type == "portfolio_timeseries":
                assert request.portfolio_timeseries_request is not None
                data_rows, page_depth = await self._collect_portfolio_timeseries_for_export(
                    portfolio_id=request.portfolio_id,
                    request=request.portfolio_timeseries_request,
                )
            else:
                assert request.position_timeseries_request is not None
                data_rows, page_depth = await self._collect_position_timeseries_for_export(
                    portfolio_id=request.portfolio_id,
                    request=request.position_timeseries_request,
                )
            result_payload = {
                "job_id": job_id,
                "dataset_type": request.dataset_type,
                "generated_at": datetime.now(UTC).isoformat(),
                "contract_version": "rfc_063_v1",
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
            return self._to_export_response(row)
        except AnalyticsInputError as exc:
            row = await self._mark_export_job_failed(job_id, error_message=str(exc))
            ANALYTICS_EXPORT_JOBS_TOTAL.labels(request.dataset_type, "failed").inc()
            return self._to_export_response(row)
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
        if row.status != "completed":
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
        if row.status != "completed":
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
