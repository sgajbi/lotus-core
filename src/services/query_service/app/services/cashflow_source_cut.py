"""Stable, source-owned cut identity shared by the cashflow evidence products."""

from dataclasses import dataclass
from datetime import datetime

from portfolio_common.source_data_product_metadata import stable_content_hash

from ..repositories.cashflow_repository import CashflowSourceCutEvidence


@dataclass(frozen=True)
class CashflowSourceCut:
    source_cut_id: str
    materialized_at: datetime


def build_cashflow_source_cut(
    *,
    tenant_id: str,
    portfolio_id: str,
    as_of_date: str,
    evidence: CashflowSourceCutEvidence,
) -> CashflowSourceCut:
    """Return an identity for the admitted portfolio state as of one business date.

    This intentionally excludes output-window parameters and product names.  The
    same portfolio, tenant, as-of date and source revisions therefore produce a
    comparable cut across cash movement and projection products; a restatement,
    scope change or different as-of date produces a different cut.
    """
    digest = stable_content_hash(
        {
            "cut_kind": "PortfolioCashflowEvidenceCut:v1",
            "tenant_id": tenant_id,
            "portfolio_id": portfolio_id,
            "as_of_date": as_of_date,
            "portfolio_base_currency": evidence.portfolio_base_currency,
            "cashflow_revision_count": evidence.cashflow_revision_count,
            "cashflow_revision_digest": evidence.cashflow_revision_digest,
            "settlement_revision_count": evidence.settlement_revision_count,
            "settlement_revision_digest": evidence.settlement_revision_digest,
        }
    )
    return CashflowSourceCut(
        source_cut_id=f"cashflow-source-cut:{digest.split(':', 1)[1][:24]}",
        materialized_at=evidence.materialized_at,
    )
