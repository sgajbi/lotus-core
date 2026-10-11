from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from portfolio_common.reconstruction_identity import (
    CURRENT_RESTATEMENT_VERSION,
    ProductReconstructionScope,
    ReconstructionScopeEvidence,
    build_reconstruction_scope_evidence,
)
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata
from portfolio_common.transaction_batch_lineage import TransactionBatchLineage

from ..application.transaction_query import (
    TransactionLedgerFilters,
    TransactionLedgerInputEvidence,
)
from ..dtos.transaction_dto import (
    PaginatedTransactionResponse,
    TransactionRecord,
    TransactionRecordResponse,
)
from .transaction_metadata import ledger_data_quality_status, ledger_reason_codes
from .transaction_reporting_currency import apply_transaction_reporting_currency_fields

TRANSACTION_LEDGER_POLICY_VERSION = "transaction-ledger-window-v1"

ConvertAmount = Callable[
    ...,
    Awaitable[Decimal],
]


async def transaction_records_from_rows(
    *,
    rows: list[Any],
    reporting_currency: str | None,
    as_of_date: date | None,
    convert_amount: ConvertAmount,
) -> list[TransactionRecord]:
    records: list[TransactionRecord] = []
    for row in rows:
        record = transaction_record_from_row(row)
        if reporting_currency and as_of_date is not None:
            await apply_transaction_reporting_currency_fields(
                record=record,
                reporting_currency=reporting_currency,
                as_of_date=as_of_date,
                convert_amount=convert_amount,
            )
        records.append(record)
    return records


def transaction_record_from_row(row: Any) -> TransactionRecord:
    record = TransactionRecord.model_validate(row)
    proof = record.transaction_source_evidence
    if proof is not None:
        record.realized_fx_pnl_local = proof.realized_fx_pnl_local
        record.realized_fx_pnl_base = proof.realized_fx_pnl_base
        if proof.realized_fx_pnl_local is None:
            record.realized_total_pnl_local = None
        if proof.realized_fx_pnl_base is None:
            record.realized_total_pnl_base = None
    record.costs = [cost for cost in row.costs or []]
    if row.cashflow:
        record.cashflow = row.cashflow
    return record


def paginated_transaction_ledger_response(
    *,
    portfolio_id: str,
    reporting_currency: str | None,
    total_count: int,
    skip: int,
    limit: int,
    transactions: list[TransactionRecord],
    effective_as_of_date: date | None,
    end_date: date | None,
    latest_evidence_timestamp: datetime | None,
    ledger_filters: TransactionLedgerFilters,
    input_evidence: TransactionLedgerInputEvidence,
    missing_instrument_security_ids: list[str] | None = None,
    today: Callable[[], date] = date.today,
) -> PaginatedTransactionResponse:
    missing_instrument_security_ids = missing_instrument_security_ids or []
    response_as_of_date = effective_as_of_date or end_date or today()
    return PaginatedTransactionResponse(
        portfolio_id=portfolio_id,
        reporting_currency=reporting_currency,
        total=total_count,
        skip=skip,
        limit=limit,
        transactions=transactions,
        **_transaction_ledger_proof_fields(
            portfolio_id=portfolio_id,
            reporting_currency=reporting_currency,
            total_count=total_count,
            returned_count=len(transactions),
            skip=skip,
            response_as_of_date=response_as_of_date,
            latest_evidence_timestamp=latest_evidence_timestamp,
            ledger_filters=ledger_filters,
            input_evidence=input_evidence,
            missing_instrument_security_ids=missing_instrument_security_ids,
        ),
    )


def exact_transaction_record_response(
    *,
    portfolio_id: str,
    reporting_currency: str | None,
    transaction: TransactionRecord,
    effective_as_of_date: date | None,
    latest_evidence_timestamp: datetime | None,
    ledger_filters: TransactionLedgerFilters,
    input_evidence: TransactionLedgerInputEvidence,
    missing_instrument_security_ids: list[str] | None = None,
) -> TransactionRecordResponse:
    """Build one exact record without weakening the ledger product proof contract."""

    missing_instrument_security_ids = missing_instrument_security_ids or []
    response_as_of_date = effective_as_of_date or transaction.transaction_date.date()
    return TransactionRecordResponse(
        portfolio_id=portfolio_id,
        reporting_currency=reporting_currency,
        transaction=transaction,
        **_transaction_ledger_proof_fields(
            portfolio_id=portfolio_id,
            reporting_currency=reporting_currency,
            total_count=1,
            returned_count=1,
            skip=0,
            response_as_of_date=response_as_of_date,
            latest_evidence_timestamp=latest_evidence_timestamp,
            ledger_filters=ledger_filters,
            input_evidence=input_evidence,
            missing_instrument_security_ids=missing_instrument_security_ids,
        ),
    )


def _transaction_ledger_proof_fields(
    *,
    portfolio_id: str,
    reporting_currency: str | None,
    total_count: int,
    returned_count: int,
    skip: int,
    response_as_of_date: date,
    latest_evidence_timestamp: datetime | None,
    ledger_filters: TransactionLedgerFilters,
    input_evidence: TransactionLedgerInputEvidence,
    missing_instrument_security_ids: list[str],
) -> dict[str, object]:
    reconstruction_evidence = transaction_ledger_reconstruction_evidence(
        portfolio_id=portfolio_id,
        response_as_of_date=response_as_of_date,
        reporting_currency=reporting_currency,
        total_count=total_count,
        latest_evidence_timestamp=latest_evidence_timestamp,
        ledger_filters=ledger_filters,
        input_evidence=input_evidence,
    )
    source_ref = (
        "lotus-core://source/TransactionLedgerWindow/"
        f"{portfolio_id}/{response_as_of_date.isoformat()}"
    )
    if ledger_filters.transaction_id is not None:
        source_ref = f"{source_ref}/transactions/{ledger_filters.transaction_id}"
    batch = input_evidence.transaction_batch_lineage or TransactionBatchLineage(
        reason="LEGACY_UNKNOWN"
    )
    return {
        **source_data_product_runtime_metadata(
            as_of_date=response_as_of_date,
            data_quality_status=ledger_data_quality_status(
                total_count=total_count,
                returned_count=returned_count,
                skip=skip,
                missing_instrument_security_ids=missing_instrument_security_ids,
            ),
            latest_evidence_timestamp=latest_evidence_timestamp,
            snapshot_id=reconstruction_evidence.scope_id,
            source_batch_fingerprint=(
                batch.fingerprint(tenant_id=ledger_filters.tenant_id.value)
                if ledger_filters.tenant_id is not None
                else None
            ),
            source_evidence_current=input_evidence.source_cut_sha256 is not None,
            freshness_status="CURRENT" if input_evidence.source_cut_sha256 else "UNAVAILABLE",
            policy_version=TRANSACTION_LEDGER_POLICY_VERSION,
            source_refs=[source_ref],
            lineage={
                "source_owner": "lotus-core",
                "source_product": "TransactionLedgerWindow",
                "source_product_version": "v1",
                **reconstruction_evidence.lineage(),
                **batch.lineage(),
            },
        ),
        "source_cut_sha256": input_evidence.source_cut_sha256,
        "reason_codes": ledger_reason_codes(
            total_count=total_count,
            returned_count=returned_count,
            skip=skip,
            missing_instrument_security_ids=missing_instrument_security_ids,
        ),
        "missing_instrument_reference_count": len(missing_instrument_security_ids),
        "missing_instrument_security_ids": missing_instrument_security_ids,
    }


def transaction_ledger_reconstruction_evidence(
    *,
    portfolio_id: str,
    response_as_of_date: date,
    reporting_currency: str | None,
    total_count: int,
    latest_evidence_timestamp: datetime | None,
    ledger_filters: TransactionLedgerFilters,
    input_evidence: TransactionLedgerInputEvidence,
) -> ReconstructionScopeEvidence:
    """Bind the complete unpaginated ledger scope to deterministic runtime evidence."""

    if ledger_filters.portfolio_id != portfolio_id:
        raise ValueError("ledger_filters.portfolio_id must match portfolio_id")
    if input_evidence.transaction_count != total_count:
        raise ValueError("input_evidence.transaction_count must match total_count")
    if input_evidence.latest_evidence_timestamp != latest_evidence_timestamp:
        raise ValueError(
            "input_evidence.latest_evidence_timestamp must match latest_evidence_timestamp"
        )
    qualifiers = _transaction_ledger_qualifiers(
        ledger_filters=ledger_filters,
        reporting_currency=reporting_currency,
    )
    return build_reconstruction_scope_evidence(
        ProductReconstructionScope(
            product="TransactionLedgerWindow",
            portfolio_id=portfolio_id,
            as_of_date=response_as_of_date,
            source_data_products=("TransactionLedgerWindow",),
            restatement_version=CURRENT_RESTATEMENT_VERSION,
            policy_version=TRANSACTION_LEDGER_POLICY_VERSION,
            qualifiers=qualifiers,
            material_evidence=(
                ("matching_transaction_count", total_count),
                ("latest_evidence_timestamp", latest_evidence_timestamp),
                ("transaction_digest", input_evidence.transaction_digest),
                ("transaction_cost_digest", input_evidence.transaction_cost_digest),
                ("selected_cashflow_digest", input_evidence.selected_cashflow_digest),
                ("selected_fx_rate_digest", input_evidence.selected_fx_rate_digest),
                ("source_cut_sha256", input_evidence.source_cut_sha256),
            ),
        )
    )


def _transaction_ledger_qualifiers(
    *,
    ledger_filters: TransactionLedgerFilters,
    reporting_currency: str | None,
) -> tuple[tuple[str, object], ...]:
    legacy_ledger_qualifiers: tuple[tuple[str, object], ...] = (
        ("instrument_id", ledger_filters.instrument_id),
        ("security_id", ledger_filters.security_id),
        ("transaction_type", ledger_filters.transaction_type),
        ("component_type", ledger_filters.component_type),
        (
            "linked_transaction_group_id",
            ledger_filters.linked_transaction_group_id,
        ),
        ("fx_contract_id", ledger_filters.fx_contract_id),
        ("swap_event_id", ledger_filters.swap_event_id),
        ("near_leg_group_id", ledger_filters.near_leg_group_id),
        ("far_leg_group_id", ledger_filters.far_leg_group_id),
        ("start_date", ledger_filters.start_date),
        ("end_date", ledger_filters.end_date),
        ("as_of_date", ledger_filters.as_of_date),
        ("reporting_currency", reporting_currency),
    )
    if ledger_filters.transaction_id is None:
        qualifiers = legacy_ledger_qualifiers
    else:
        qualifiers = (("transaction_id", ledger_filters.transaction_id), *legacy_ledger_qualifiers)
    qualifiers = (
        *(
            (("source_system", ledger_filters.source_system),)
            if ledger_filters.source_system
            else ()
        ),
        *(
            (("source_batch_id", ledger_filters.source_batch_id),)
            if ledger_filters.source_batch_id
            else ()
        ),
        *qualifiers,
    )
    if ledger_filters.tenant_id is None:
        return qualifiers
    return (
        ("tenant_id", ledger_filters.tenant_id.value),
        ("source_evidence_selection", ledger_filters.source_evidence_selection),
        ("source_revision_id", ledger_filters.source_revision_id),
        *qualifiers,
    )
