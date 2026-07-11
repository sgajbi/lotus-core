"""Application use cases for client liquidity-planning source evidence."""

from collections.abc import Sequence
from datetime import date
from typing import Literal, cast

from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata

from ..contracts.client_liquidity_evidence import (
    ClientIncomeNeedsScheduleEntry,
    ClientIncomeNeedsScheduleRequest,
    ClientIncomeNeedsScheduleResponse,
    ClientIncomeNeedsScheduleSupportability,
    LiquidityReserveRequirementEntry,
    LiquidityReserveRequirementRequest,
    LiquidityReserveRequirementResponse,
    LiquidityReserveRequirementSupportability,
    PlannedWithdrawalScheduleEntry,
    PlannedWithdrawalScheduleRequest,
    PlannedWithdrawalScheduleResponse,
    PlannedWithdrawalScheduleSupportability,
)
from ..domain.client_liquidity_evidence import (
    ClientIncomeNeedSourceRecord,
    LiquidityReserveRequirementSourceRecord,
    PlannedWithdrawalSourceRecord,
)
from ..domain.effective_mandate import EffectiveMandateBinding
from ..ports.client_liquidity_evidence import ClientLiquidityEvidenceReader
from ..ports.effective_mandate import EffectiveMandateReader
from .source_evidence import latest_evidence_timestamp


class ClientLiquidityEvidenceService:
    """Resolve source-owned income, reserve, and withdrawal evidence."""

    def __init__(
        self,
        *,
        mandate_reader: EffectiveMandateReader,
        reader: ClientLiquidityEvidenceReader,
        clock: Clock,
    ) -> None:
        self._mandate_reader = mandate_reader
        self._reader = reader
        self._clock = clock

    async def get_client_income_needs_schedule(
        self, *, portfolio_id: str, request: ClientIncomeNeedsScheduleRequest
    ) -> ClientIncomeNeedsScheduleResponse | None:
        binding = await self._resolve_binding(portfolio_id, request.as_of_date, request.mandate_id)
        if binding is None:
            return None
        records = await self._reader.list_income_needs(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_schedules=request.include_inactive_schedules,
        )
        entries = [_income_entry(record) for record in records]
        state, reason, missing = _supportability(
            present=bool(records),
            ready_reason="CLIENT_INCOME_NEEDS_SCHEDULE_READY",
            empty_reason="CLIENT_INCOME_NEEDS_SCHEDULE_EMPTY",
            missing_family="client_income_needs_schedule",
        )
        return ClientIncomeNeedsScheduleResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            schedules=entries,
            supportability=ClientIncomeNeedsScheduleSupportability(
                state=state,
                reason=reason,
                schedule_count=len(entries),
                missing_data_families=missing,
            ),
            lineage=_lineage(
                "client_income_needs_schedules",
                "rfc_042_client_income_needs_schedule_v1",
            ),
            **self._runtime_metadata(
                portfolio_id=portfolio_id,
                binding=binding,
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                records=records,
                product_key="client_income_needs_schedule",
            ),
        )

    async def get_liquidity_reserve_requirement(
        self, *, portfolio_id: str, request: LiquidityReserveRequirementRequest
    ) -> LiquidityReserveRequirementResponse | None:
        binding = await self._resolve_binding(portfolio_id, request.as_of_date, request.mandate_id)
        if binding is None:
            return None
        records = await self._reader.list_reserve_requirements(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_requirements=request.include_inactive_requirements,
        )
        entries = [_reserve_entry(record) for record in records]
        state, reason, missing = _supportability(
            present=bool(records),
            ready_reason="LIQUIDITY_RESERVE_REQUIREMENT_READY",
            empty_reason="LIQUIDITY_RESERVE_REQUIREMENT_EMPTY",
            missing_family="liquidity_reserve_requirement",
        )
        return LiquidityReserveRequirementResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            requirements=entries,
            supportability=LiquidityReserveRequirementSupportability(
                state=state,
                reason=reason,
                requirement_count=len(entries),
                missing_data_families=missing,
            ),
            lineage=_lineage(
                "liquidity_reserve_requirements",
                "rfc_042_liquidity_reserve_requirement_v1",
            ),
            **self._runtime_metadata(
                portfolio_id=portfolio_id,
                binding=binding,
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                records=records,
                product_key="liquidity_reserve_requirement",
            ),
        )

    async def get_planned_withdrawal_schedule(
        self, *, portfolio_id: str, request: PlannedWithdrawalScheduleRequest
    ) -> PlannedWithdrawalScheduleResponse | None:
        binding = await self._resolve_binding(portfolio_id, request.as_of_date, request.mandate_id)
        if binding is None:
            return None
        records = await self._reader.list_planned_withdrawals(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            horizon_days=request.horizon_days,
            mandate_id=binding.mandate_id,
            include_inactive_withdrawals=request.include_inactive_withdrawals,
        )
        entries = [_withdrawal_entry(record) for record in records]
        state, reason, missing = _supportability(
            present=bool(records),
            ready_reason="PLANNED_WITHDRAWAL_SCHEDULE_READY",
            empty_reason="PLANNED_WITHDRAWAL_SCHEDULE_EMPTY",
            missing_family="planned_withdrawal_schedule",
        )
        return PlannedWithdrawalScheduleResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            horizon_days=request.horizon_days,
            withdrawals=entries,
            supportability=PlannedWithdrawalScheduleSupportability(
                state=state,
                reason=reason,
                withdrawal_count=len(entries),
                missing_data_families=missing,
            ),
            lineage=_lineage(
                "planned_withdrawal_schedules",
                "rfc_042_planned_withdrawal_schedule_v1",
            ),
            **self._runtime_metadata(
                portfolio_id=portfolio_id,
                binding=binding,
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                records=records,
                product_key="planned_withdrawal_schedule",
                fingerprint_fields={"horizon_days": request.horizon_days},
            ),
        )

    async def _resolve_binding(
        self, portfolio_id: str, as_of_date: date, mandate_id: str | None
    ) -> EffectiveMandateBinding | None:
        return await self._mandate_reader.resolve(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            mandate_id=mandate_id,
        )

    def _runtime_metadata(
        self,
        *,
        portfolio_id: str,
        binding: EffectiveMandateBinding,
        as_of_date: date,
        tenant_id: str | None,
        records: Sequence[object],
        product_key: str,
        fingerprint_fields: dict[str, object] | None = None,
    ) -> dict[str, object]:
        identity = {
            "portfolio_id": portfolio_id,
            "client_id": binding.client_id,
            "as_of_date": as_of_date.isoformat(),
            **(fingerprint_fields or {}),
        }
        return cast(
            dict[str, object],
            source_data_product_runtime_metadata(
                as_of_date=as_of_date,
                generated_at=self._clock.utc_now(),
                tenant_id=tenant_id,
                data_quality_status=("ACCEPTED" if records else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp([binding], records),
                source_batch_fingerprint=None,
                snapshot_id=f"{product_key}:{request_fingerprint(identity)}",
            ),
        )


def _supportability(
    *, present: bool, ready_reason: str, empty_reason: str, missing_family: str
) -> tuple[Literal["READY", "INCOMPLETE", "UNAVAILABLE"], str, list[str]]:
    if present:
        return "READY", ready_reason, []
    return "INCOMPLETE", empty_reason, [missing_family]


def _lineage(source_table: str, contract_version: str) -> dict[str, str]:
    return {
        "source_system": "lotus-core-query-service",
        "source_table": f"{source_table},portfolio_mandate_bindings",
        "contract_version": contract_version,
    }


def _income_entry(record: ClientIncomeNeedSourceRecord) -> ClientIncomeNeedsScheduleEntry:
    return ClientIncomeNeedsScheduleEntry(
        schedule_id=record.schedule_id,
        need_type=record.need_type,
        need_status=record.need_status,
        amount=record.amount,
        currency=record.currency,
        frequency=record.frequency,
        start_date=record.start_date,
        end_date=record.end_date,
        priority=record.priority,
        funding_policy=record.funding_policy,
        source_record_id=record.source_record_id,
    )


def _reserve_entry(
    record: LiquidityReserveRequirementSourceRecord,
) -> LiquidityReserveRequirementEntry:
    return LiquidityReserveRequirementEntry(
        reserve_requirement_id=record.reserve_requirement_id,
        reserve_type=record.reserve_type,
        reserve_status=record.reserve_status,
        required_amount=record.required_amount,
        currency=record.currency,
        horizon_days=record.horizon_days,
        priority=record.priority,
        policy_source=record.policy_source,
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        requirement_version=record.requirement_version,
        source_record_id=record.source_record_id,
    )


def _withdrawal_entry(record: PlannedWithdrawalSourceRecord) -> PlannedWithdrawalScheduleEntry:
    return PlannedWithdrawalScheduleEntry(
        withdrawal_schedule_id=record.withdrawal_schedule_id,
        withdrawal_type=record.withdrawal_type,
        withdrawal_status=record.withdrawal_status,
        amount=record.amount,
        currency=record.currency,
        scheduled_date=record.scheduled_date,
        recurrence_frequency=record.recurrence_frequency,
        purpose_code=record.purpose_code,
        source_record_id=record.source_record_id,
    )
