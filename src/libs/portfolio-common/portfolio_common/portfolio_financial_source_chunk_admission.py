"""Bounded retained-ingress typed translation at the neutral source admission boundary."""

import json

from pydantic import TypeAdapter

from .domain.calculation_lineage import canonical_content_hash
from .domain.portfolio_financial_source_cuts import SourceCutIdentity
from .portfolio_financial_source_cut_admission import (
    MAX_CHUNK_BYTES,
    MAX_CHUNK_ROWS,
    FinancialInput,
    RegistryMemberInput,
    closed_source_json,
)


def retained_chunk_commitment(
    identity: SourceCutIdentity, raw_bytes: bytes, *, registry: bool, chunk_index: int
) -> tuple[int, str]:
    """Decode retained ingress at admission; expose only a plain count and typed hash."""
    body = closed_source_json(raw_bytes.decode("utf-8"))
    collection = "members" if registry else "selections"
    expected_keys = {
        "source_system",
        "registry_scope_id",
        "source_cut_id",
        "revision",
        "chunk_index",
        "typed_content_hash",
        collection,
    }
    if type(body) is not dict or set(body) != expected_keys:
        raise ValueError("closed chunk object required")
    address = (
        identity.source_system,
        identity.scope_id,
        identity.source_cut_id,
        identity.revision,
    )
    if (
        tuple(
            body[key] for key in ("source_system", "registry_scope_id", "source_cut_id", "revision")
        )
        != address
    ):
        raise ValueError("chunk address substitution")
    if (
        type(body["revision"]) is not int
        or type(body["chunk_index"]) is not int
        or body["chunk_index"] != chunk_index
    ):
        raise ValueError("chunk index substitution")
    records = TypeAdapter(
        tuple[RegistryMemberInput, ...] if registry else tuple[FinancialInput, ...]
    ).validate_json(json.dumps(body[collection]))
    if len(records) > MAX_CHUNK_ROWS or len(raw_bytes) > MAX_CHUNK_BYTES:
        raise ValueError("chunk byte or row count mismatch")
    typed_hash = canonical_content_hash(
        {
            "contract": "PortfolioHistoricalRegistryChunk:v1"
            if registry
            else "PortfolioFinancialSourceCutChunk:v1",
            collection: [record.to_domain().content_hash for record in records]
            if registry
            else [record.model_dump(mode="json") for record in records],
        }
    )
    if typed_hash != body["typed_content_hash"]:
        raise ValueError("chunk typed drift")
    return len(records), typed_hash
