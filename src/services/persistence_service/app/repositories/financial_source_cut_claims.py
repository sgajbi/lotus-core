"""Exact source command identity and database-time claim/fence transactions."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.portfolio_financial_source_cut_decoding import source_manifest_from_payload
from portfolio_common.portfolio_financial_source_cut_models import (
    SCOPE,
    FinancialSourceCutWorkRow,
)
from sqlalchemy import and_, func, or_, select, update

from ..ports.financial_source_cut_work import (
    SourceCutClaim,
    SourceManifestRejected,
    StaleSourceCutClaim,
)


def scope(row):
    return {name: getattr(row, name) for name in SCOPE}


def predicates(model, row):
    return [getattr(model, key) == value for key, value in scope(row).items()]


def claim_scope_hash(row):
    return canonical_content_hash({**scope(row), "partition_index": row.partition_index})


def manifest_from_row(row):
    if row is None:
        raise SourceManifestRejected("SOURCE_MANIFEST_MISSING")
    body = row.declaration
    header_keys = {
        "source_system",
        "registry_scope_id",
        "source_cut_id",
        "revision",
        "definition_version",
        "coverage_from",
        "coverage_to",
        "calendar",
        "observed_at",
        "generated_at",
        "predecessor_hash",
        "expected_head_hash",
    }
    registry_keys = {
        "expected_population",
        "declared_coverage",
        "supplied_count",
        "members_root",
        "chunk_count",
        "chunks_root",
    }
    financial_keys = {"selection_count", "selections_root", "chunk_count", "chunks_root"}
    if (
        row.product_name not in {"PortfolioHistoricalRegistry", "PortfolioFinancialSourceCut"}
        or type(body) is not dict
    ):
        raise SourceManifestRejected("SOURCE_MANIFEST_DECLARATION_INVALID")
    if set(body) != header_keys | (
        registry_keys if row.product_name == "PortfolioHistoricalRegistry" else financial_keys
    ):
        raise SourceManifestRejected("SOURCE_MANIFEST_DECLARATION_INVALID")
    if any(
        body[key] != getattr(row, key)
        for key in ("source_system", "registry_scope_id", "source_cut_id", "revision")
    ):
        raise SourceManifestRejected("SOURCE_MANIFEST_SCOPE_DRIFT")
    try:
        manifest = source_manifest_from_payload(body, row.tenant_id, row.product_name)
    except ValueError as error:
        raise SourceManifestRejected("SOURCE_MANIFEST_DECLARATION_INVALID") from error
    if manifest.content_hash != row.content_hash:
        raise SourceManifestRejected("SOURCE_MANIFEST_TYPED_DRIFT")
    return manifest


def require_claim(row, claim: SourceCutClaim, now) -> None:
    if (
        row is None
        or row.status != "CLAIMED"
        or row.tenant_id != claim.tenant_id
        or row.work_id != claim.work_id
        or row.content_hash != claim.command_hash
        or row.lease_token != claim.lease_token
        or row.lease_expires_at != claim.lease_expires_at
        or row.lease_expires_at <= now
        or canonical_content_hash(row.checkpoint) != claim.checkpoint_hash
        or claim_scope_hash(row) != claim.scope_hash
    ):
        raise StaleSourceCutClaim("SOURCE_CUT_CLAIM_STALE")


class FinancialSourceCutClaims:
    def __init__(self, session_factory, *, lease_seconds=30, retry_seconds=5):
        if not 10 <= lease_seconds <= 300 or not 1 <= retry_seconds <= 60:
            raise ValueError("bounded capture lease/backoff required")
        self.sessions = session_factory
        self.lease_seconds = lease_seconds
        self.retry_seconds = retry_seconds
        self.last_tenant_id = None

    async def claim(self):
        async with self.sessions() as session, session.begin():
            now = await session.scalar(select(func.clock_timestamp()))
            eligible = or_(
                and_(
                    FinancialSourceCutWorkRow.status == "PENDING",
                    FinancialSourceCutWorkRow.available_at <= now,
                ),
                and_(
                    FinancialSourceCutWorkRow.status == "CLAIMED",
                    FinancialSourceCutWorkRow.lease_expires_at <= now,
                ),
            )
            tenants = (
                select(FinancialSourceCutWorkRow.tenant_id)
                .where(eligible)
                .order_by(FinancialSourceCutWorkRow.tenant_id)
                .limit(1)
            )
            tenant = (
                await session.scalar(
                    tenants.where(FinancialSourceCutWorkRow.tenant_id > self.last_tenant_id)
                )
                if self.last_tenant_id is not None
                else None
            )
            if tenant is None:
                tenant = await session.scalar(tenants)
            if tenant is None:
                return None
            row = await session.scalar(
                select(FinancialSourceCutWorkRow)
                .where(eligible, FinancialSourceCutWorkRow.tenant_id == tenant)
                .order_by(FinancialSourceCutWorkRow.available_at, FinancialSourceCutWorkRow.work_id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return None
            self.last_tenant_id = tenant
            row.status = "CLAIMED"
            row.lease_token = str(uuid4())
            row.lease_expires_at = await session.scalar(select(func.clock_timestamp())) + timedelta(
                seconds=self.lease_seconds
            )
            row.attempts += 1
            return SourceCutClaim(
                row.work_id,
                row.tenant_id,
                row.content_hash,
                row.lease_token,
                row.lease_expires_at,
                canonical_content_hash(row.checkpoint),
                claim_scope_hash(row),
            )

    async def locked(self, session, claim):
        row = await session.scalar(
            select(FinancialSourceCutWorkRow)
            .where(
                FinancialSourceCutWorkRow.work_id == claim.work_id,
                FinancialSourceCutWorkRow.tenant_id == claim.tenant_id,
            )
            .with_for_update()
        )
        require_claim(row, claim, await session.scalar(select(func.clock_timestamp())))
        return row

    async def release(self, session, row, claim, checkpoint, *, status="PENDING", error=None):
        result = await session.execute(
            update(FinancialSourceCutWorkRow)
            .where(
                FinancialSourceCutWorkRow.work_id == claim.work_id,
                FinancialSourceCutWorkRow.tenant_id == claim.tenant_id,
                FinancialSourceCutWorkRow.status == "CLAIMED",
                FinancialSourceCutWorkRow.lease_token == claim.lease_token,
                FinancialSourceCutWorkRow.content_hash == claim.command_hash,
                FinancialSourceCutWorkRow.lease_expires_at > func.clock_timestamp(),
            )
            .values(
                status=status,
                lease_token=None,
                lease_expires_at=None,
                checkpoint=checkpoint,
                last_error_code=error,
                available_at=func.clock_timestamp()
                + timedelta(seconds=self.retry_seconds if error else 0),
            )
            .returning(FinancialSourceCutWorkRow.work_id)
        )
        if result.scalar_one_or_none() is None:
            raise StaleSourceCutClaim("SOURCE_CUT_LEASE_EXPIRED_BEFORE_COMMIT")

    async def renew(self, session, row, claim):
        expiry = await session.scalar(
            update(FinancialSourceCutWorkRow)
            .where(
                FinancialSourceCutWorkRow.work_id == claim.work_id,
                FinancialSourceCutWorkRow.tenant_id == claim.tenant_id,
                FinancialSourceCutWorkRow.lease_token == claim.lease_token,
                FinancialSourceCutWorkRow.status == "CLAIMED",
                FinancialSourceCutWorkRow.content_hash == claim.command_hash,
                FinancialSourceCutWorkRow.lease_expires_at > func.clock_timestamp(),
            )
            .values(lease_expires_at=func.clock_timestamp() + timedelta(seconds=self.lease_seconds))
            .returning(FinancialSourceCutWorkRow.lease_expires_at)
        )
        if expiry is None:
            raise StaleSourceCutClaim("SOURCE_CUT_LEASE_EXPIRED_BEFORE_RENEWAL")
        return replace(claim, lease_expires_at=expiry)
