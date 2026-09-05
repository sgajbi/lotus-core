"""Bound caller-sized PostgreSQL statements by rows and bind parameters."""

import logging
from collections.abc import Iterator, Sequence
from enum import StrEnum
from math import ceil
from typing import TypeVar

POSTGRES_STATEMENT_ROW_LIMIT = 1_000
POSTGRES_BIND_PARAMETER_BUDGET = 32_000

_T = TypeVar("_T")
logger = logging.getLogger(__name__)


class StatementBatchOperation(StrEnum):
    """Governed low-cardinality operation labels for oversized statements."""

    POSITION_STATE_BULK_UPDATE = "position_state_bulk_update"
    POSITION_WATERMARK_UPDATE = "position_watermark_update"
    VALUATION_JOB_UPSERT = "valuation_job_upsert"
    VALUATION_JOB_EPOCH_LOOKUP = "valuation_job_epoch_lookup"
    CONTIGUOUS_SNAPSHOT_LOOKUP = "contiguous_snapshot_lookup"
    FIRST_OPEN_DATE_LOOKUP = "first_open_date_lookup"
    DISPATCH_RECOVERY_UPDATE = "dispatch_recovery_update"
    VALUATION_STALE_SUPERSEDED_UPDATE = "valuation_stale_superseded_update"
    VALUATION_STALE_FAILED_UPDATE = "valuation_stale_failed_update"
    VALUATION_STALE_RESET_UPDATE = "valuation_stale_reset_update"
    REPROCESSING_STALE_FAILED_UPDATE = "reprocessing_stale_failed_update"
    REPROCESSING_STALE_RESET_UPDATE = "reprocessing_stale_reset_update"
    REPROCESSING_INVALID_PAYLOAD_UPDATE = "reprocessing_invalid_payload_update"
    DPM_INSTRUMENT_ELIGIBILITY_LOOKUP = "dpm_instrument_eligibility_lookup"
    DPM_TAX_LOT_LOOKUP = "dpm_tax_lot_lookup"
    DPM_INSTRUMENT_REFERENCE_LOOKUP = "dpm_instrument_reference_lookup"
    DPM_MARKET_PRICE_LOOKUP = "dpm_market_price_lookup"
    DPM_FX_RATE_LOOKUP = "dpm_fx_rate_lookup"
    AGGREGATION_STALE_FAILED_UPDATE = "aggregation_stale_failed_update"
    AGGREGATION_STALE_REQUEUE_UPDATE = "aggregation_stale_requeue_update"
    FINANCIAL_RECONCILIATION_FX_LOOKUP = "financial_reconciliation_fx_lookup"


def statement_chunk_size(
    *,
    binds_per_row: int,
    reserved_binds: int = 0,
    row_limit: int = POSTGRES_STATEMENT_ROW_LIMIT,
    bind_budget: int = POSTGRES_BIND_PARAMETER_BUDGET,
) -> int:
    """Return the largest safe row count for one parameterized statement.

    ``reserved_binds`` accounts for scalar predicates or values outside the
    caller-sized row collection.  Invalid budgets fail before repository I/O.
    """

    if binds_per_row <= 0:
        raise ValueError("binds_per_row must be a positive integer")
    if reserved_binds < 0:
        raise ValueError("reserved_binds must be non-negative")
    if row_limit <= 0:
        raise ValueError("row_limit must be a positive integer")
    if bind_budget <= 0:
        raise ValueError("bind_budget must be a positive integer")
    available_binds = bind_budget - reserved_binds
    if available_binds < binds_per_row:
        raise ValueError("bind budget cannot accommodate one row")
    return min(row_limit, available_binds // binds_per_row)


def iter_statement_chunks(
    values: Sequence[_T],
    *,
    binds_per_row: int,
    reserved_binds: int = 0,
) -> Iterator[Sequence[_T]]:
    """Yield order-preserving statement chunks within the governed budget."""

    chunk_size = statement_chunk_size(
        binds_per_row=binds_per_row,
        reserved_binds=reserved_binds,
    )
    for start in range(0, len(values), chunk_size):
        yield values[start : start + chunk_size]


def observe_multi_statement_batch(
    *,
    operation: StatementBatchOperation,
    item_count: int,
    binds_per_row: int,
    reserved_binds: int = 0,
) -> None:
    """Emit one identifier-free support event when an operation needs many statements."""

    chunk_size = statement_chunk_size(
        binds_per_row=binds_per_row,
        reserved_binds=reserved_binds,
    )
    chunk_count = ceil(item_count / chunk_size) if item_count else 0
    if chunk_count <= 1:
        return
    logger.info(
        "Bounded oversized repository operation across multiple statements.",
        extra={
            "event_name": "database_statement_batch",
            "operation": operation.value,
            "status": "bounded",
            "reason_code": "row_or_bind_budget",
            "item_count": item_count,
            "chunk_count": chunk_count,
            "max_rows_per_statement": chunk_size,
        },
    )
