from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import Depends
from portfolio_common.database_models import (
    BenchmarkCompositionSeries,
    BenchmarkDefinition,
    BenchmarkReturnSeries,
    CashAccountMaster,
    ClassificationTaxonomy,
    IndexDefinition,
    IndexPriceSeries,
    IndexReturnSeries,
    InstrumentEligibilityProfile,
    InstrumentLookthroughComponent,
    ModelPortfolioDefinition,
    ModelPortfolioTarget,
    PortfolioBenchmarkAssignment,
    PortfolioMandateBinding,
    RiskFreeSeries,
)
from portfolio_common.db import get_async_db_session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class ReferenceDataIngestionService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def upsert_portfolio_benchmark_assignments(self, records: list[dict[str, Any]]) -> None:
        now = datetime.now(UTC)
        normalized_records = []
        for record in records:
            row = dict(record)
            if row.get("assignment_recorded_at") is None:
                row["assignment_recorded_at"] = now
            normalized_records.append(row)
        await self._upsert_many(
            model=PortfolioBenchmarkAssignment,
            records=normalized_records,
            conflict_columns=[
                "portfolio_id",
                "benchmark_id",
                "effective_from",
                "assignment_version",
            ],
            update_columns=[
                "effective_to",
                "assignment_source",
                "assignment_status",
                "policy_pack_id",
                "source_system",
                "assignment_recorded_at",
            ],
        )

    async def upsert_model_portfolio_definitions(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=ModelPortfolioDefinition,
            records=records,
            conflict_columns=[
                "model_portfolio_id",
                "model_portfolio_version",
                "effective_from",
            ],
            update_columns=[
                "display_name",
                "base_currency",
                "risk_profile",
                "mandate_type",
                "rebalance_frequency",
                "approval_status",
                "approved_at",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        )

    async def upsert_model_portfolio_targets(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=ModelPortfolioTarget,
            records=records,
            conflict_columns=[
                "model_portfolio_id",
                "model_portfolio_version",
                "instrument_id",
                "effective_from",
            ],
            update_columns=[
                "target_weight",
                "min_weight",
                "max_weight",
                "target_status",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        )

    async def upsert_discretionary_mandate_bindings(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=PortfolioMandateBinding,
            records=records,
            conflict_columns=[
                "portfolio_id",
                "mandate_id",
                "effective_from",
                "binding_version",
            ],
            update_columns=[
                "client_id",
                "mandate_type",
                "discretionary_authority_status",
                "booking_center_code",
                "jurisdiction_code",
                "model_portfolio_id",
                "policy_pack_id",
                "risk_profile",
                "investment_horizon",
                "leverage_allowed",
                "tax_awareness_allowed",
                "settlement_awareness_required",
                "rebalance_frequency",
                "rebalance_bands",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        )

    async def upsert_instrument_eligibility_profiles(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=InstrumentEligibilityProfile,
            records=records,
            conflict_columns=[
                "security_id",
                "effective_from",
                "eligibility_version",
            ],
            update_columns=[
                "eligibility_status",
                "product_shelf_status",
                "buy_allowed",
                "sell_allowed",
                "restriction_reason_codes",
                "restriction_rationale",
                "settlement_days",
                "settlement_calendar_id",
                "liquidity_tier",
                "issuer_id",
                "issuer_name",
                "ultimate_parent_issuer_id",
                "ultimate_parent_issuer_name",
                "asset_class",
                "country_of_risk",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        )

    async def upsert_benchmark_definitions(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=BenchmarkDefinition,
            records=records,
            conflict_columns=["benchmark_id", "effective_from"],
            update_columns=[
                "benchmark_name",
                "benchmark_type",
                "benchmark_currency",
                "return_convention",
                "benchmark_status",
                "benchmark_family",
                "benchmark_provider",
                "rebalance_frequency",
                "classification_set_id",
                "classification_labels",
                "effective_to",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        )

    async def upsert_benchmark_compositions(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=BenchmarkCompositionSeries,
            records=records,
            conflict_columns=["benchmark_id", "index_id", "composition_effective_from"],
            update_columns=[
                "composition_effective_to",
                "composition_weight",
                "rebalance_event_id",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        )

    async def upsert_indices(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=IndexDefinition,
            records=records,
            conflict_columns=["index_id", "effective_from"],
            update_columns=[
                "index_name",
                "index_currency",
                "index_type",
                "index_status",
                "index_provider",
                "index_market",
                "classification_set_id",
                "classification_labels",
                "effective_to",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        )

    async def upsert_index_price_series(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=IndexPriceSeries,
            records=records,
            conflict_columns=["series_id", "index_id", "series_date"],
            update_columns=[
                "index_price",
                "series_currency",
                "value_convention",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        )

    async def upsert_index_return_series(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=IndexReturnSeries,
            records=records,
            conflict_columns=["series_id", "index_id", "series_date"],
            update_columns=[
                "index_return",
                "return_period",
                "return_convention",
                "series_currency",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        )

    async def upsert_benchmark_return_series(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=BenchmarkReturnSeries,
            records=records,
            conflict_columns=["series_id", "benchmark_id", "series_date"],
            update_columns=[
                "benchmark_return",
                "return_period",
                "return_convention",
                "series_currency",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        )

    async def upsert_risk_free_series(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=RiskFreeSeries,
            records=records,
            conflict_columns=["series_id", "risk_free_curve_id", "series_date"],
            update_columns=[
                "value",
                "value_convention",
                "day_count_convention",
                "compounding_convention",
                "series_currency",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        )

    async def upsert_classification_taxonomy(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=ClassificationTaxonomy,
            records=records,
            conflict_columns=[
                "classification_set_id",
                "taxonomy_scope",
                "dimension_name",
                "dimension_value",
                "effective_from",
            ],
            update_columns=[
                "dimension_description",
                "effective_to",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        )

    async def upsert_cash_account_masters(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=CashAccountMaster,
            records=records,
            conflict_columns=["cash_account_id"],
            update_columns=[
                "portfolio_id",
                "security_id",
                "display_name",
                "account_currency",
                "account_role",
                "lifecycle_status",
                "opened_on",
                "closed_on",
                "source_system",
                "source_record_id",
            ],
        )

    async def upsert_instrument_lookthrough_components(self, records: list[dict[str, Any]]) -> None:
        await self._upsert_many(
            model=InstrumentLookthroughComponent,
            records=records,
            conflict_columns=[
                "parent_security_id",
                "component_security_id",
                "effective_from",
            ],
            update_columns=[
                "effective_to",
                "component_weight",
                "source_system",
                "source_record_id",
            ],
        )

    async def _upsert_many(
        self,
        *,
        model: Any,
        records: list[dict[str, Any]],
        conflict_columns: list[str],
        update_columns: list[str],
    ) -> None:
        if not records:
            return

        now = datetime.now(UTC)
        payload = []
        for record in records:
            row = dict(record)
            row.setdefault("created_at", now)
            row["updated_at"] = now
            payload.append(row)

        stmt = insert(model).values(payload)
        update_map = {column: getattr(stmt.excluded, column) for column in update_columns}
        update_map["updated_at"] = now
        stmt = stmt.on_conflict_do_update(index_elements=conflict_columns, set_=update_map)
        await self._db.execute(stmt)
        await self._db.commit()


def get_reference_data_ingestion_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ReferenceDataIngestionService:
    return ReferenceDataIngestionService(db)
