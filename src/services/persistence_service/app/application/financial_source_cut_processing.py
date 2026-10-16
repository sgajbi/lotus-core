"""Bounded verification/capture steps; network acquisition never owns a write session."""

import hashlib

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import (
    HistoricalRegistryCut,
    OrderedContentRoot,
)
from portfolio_common.portfolio_financial_source_chunk_admission import retained_chunk_commitment
from portfolio_common.portfolio_financial_source_cut_admission import (
    financial_input_from_payload,
    registry_member_from_payload,
)

from ..ports.financial_source_captures import FinancialSourceCaptureClient, SourceCaptureUnavailable
from ..ports.financial_source_cut_work import (
    FinancialSourceCutWork,
    SourceCutProgress,
    SourceManifestRejected,
    StaleSourceCutClaim,
)


class FinancialSourceCutProcessor:
    def __init__(self, work: FinancialSourceCutWork, captures: FinancialSourceCaptureClient):
        self.work = work
        self.captures = captures

    async def step(self) -> bool:
        claim = await self.work.claim()
        if claim is None:
            return False
        try:
            request = await self.work.next_capture(claim)
            if isinstance(request, SourceCutProgress):
                await self.work.advance(claim, request)
            elif request is None:
                await self.work.complete(claim)
            else:
                page = await self.work.cached_capture(request)
                if page is None:
                    page = await self.captures.fetch(request)
                try:
                    if page.request != request:
                        raise SourceCaptureUnavailable("SOURCE_CAPTURE_REQUEST_SUBSTITUTION")
                    # Commit must recheck DB time/token/root/checkpoint after remote I/O.
                    await self.work.save_capture(claim, page)
                finally:
                    page.capture_bytes.close()
        except StaleSourceCutClaim:
            # Another worker owns progress; this claim may change nothing.
            return True
        except SourceManifestRejected:
            try:
                await self.work.reject(claim)
            except StaleSourceCutClaim:
                pass
        except SourceCaptureUnavailable:
            try:
                await self.work.defer(claim, "SOURCE_CAPTURE_UNAVAILABLE")
            except StaleSourceCutClaim:
                pass
        return True


def _accumulator(checkpoint, contract):
    saved = checkpoint.get("ordered_root_checkpoint")
    return OrderedContentRoot(contract, checkpoint=None if saved is None else tuple(saved))


def verify_chunk_step(checkpoint, manifest, chunk):
    """One admitted byte-bounded chunk, with a portable root checkpoint."""
    result = dict(checkpoint)
    root = _accumulator(checkpoint, "NeutralSourceChunks:v1")
    expected_rows = (
        manifest.supplied_count
        if isinstance(manifest, HistoricalRegistryCut)
        else manifest.selection_count
    )
    if chunk is None:
        if (
            root.finish() != (manifest.chunk_count, manifest.chunks_root)
            or result.get("verified_rows", 0) != expected_rows
        ):
            raise SourceManifestRejected("SOURCE_CHUNK_MANIFEST_MISMATCH")
        result.update(
            stage="VERIFY_MEMBERS"
            if isinstance(manifest, HistoricalRegistryCut)
            else "VERIFY_INPUTS",
            ordered_root_checkpoint=None,
        )
        return result
    if chunk.chunk_index != root.count or type(chunk.row_count) is not int or chunk.row_count < 0:
        raise SourceManifestRejected("SOURCE_CHUNK_INDEX_OR_COUNT")
    if hashlib.sha256(chunk.raw_bytes).hexdigest() != chunk.raw_hash:
        raise SourceManifestRejected("SOURCE_CHUNK_RAW_DRIFT")
    _verify_chunk_payload(manifest, chunk)
    root.append(chunk.typed_hash)
    result.update(
        ordered_root_checkpoint=list(root.checkpoint),
        verified_rows=result.get("verified_rows", 0) + chunk.row_count,
    )
    if root.count > manifest.chunk_count or result["verified_rows"] > expected_rows:
        raise SourceManifestRejected("SOURCE_CHUNK_EXCESS_POPULATION")
    return result


def _verify_chunk_payload(manifest, chunk):
    """Reconcile a framework-neutral admission commitment with retained worker state."""
    try:
        row_count, typed_hash = retained_chunk_commitment(
            manifest.identity,
            chunk.raw_bytes,
            registry=isinstance(manifest, HistoricalRegistryCut),
            chunk_index=chunk.chunk_index,
        )
        if row_count != chunk.row_count:
            raise ValueError("chunk byte or row count mismatch")
        if typed_hash != chunk.typed_hash:
            raise ValueError("chunk typed drift")
    except (ValueError, UnicodeError) as error:
        raise SourceManifestRejected("SOURCE_CHUNK_TYPED_DRIFT") from error


def verify_member_page(checkpoint, manifest, records, *, has_more):
    result = dict(checkpoint)
    root = _accumulator(checkpoint, "PortfolioHistoricalRegistryMembers:v1")
    previous = (
        tuple(result["last_member_key"]) if result.get("last_member_key") is not None else None
    )
    for row in records:
        try:
            member = registry_member_from_payload(row.declaration)
        except ValueError as error:
            raise SourceManifestRejected("SOURCE_MEMBER_DECLARATION_INVALID") from error
        key = (member.provider_namespace, member.source_member_id)
        if (
            member.content_hash != row.content_hash
            or key != (row.provider_namespace, row.source_member_id)
            or (previous is not None and key <= previous)
        ):
            raise SourceManifestRejected("SOURCE_MEMBER_TYPED_ORDER_DRIFT")
        root.append(member.content_hash)
        previous = key
    result.update(
        ordered_root_checkpoint=list(root.checkpoint),
        last_member_key=None if previous is None else list(previous),
    )
    if root.count > manifest.supplied_count:
        raise SourceManifestRejected("SOURCE_MEMBER_EXCESS_POPULATION")
    if not has_more:
        if root.finish() != (manifest.supplied_count, manifest.members_root):
            raise SourceManifestRejected("SOURCE_MEMBER_POPULATION_MISMATCH")
        result.update(stage="READY", ordered_root_checkpoint=None)
    return result


def verify_input_page(checkpoint, manifest, records, *, has_more):
    result = dict(checkpoint)
    root = _accumulator(checkpoint, "PortfolioFinancialSourceCutInputs:v1")
    previous = result.get("last_verified_portfolio_id")
    for row in records:
        try:
            graph = financial_input_from_payload(manifest.identity, row.declaration)
        except ValueError as error:
            raise SourceManifestRejected("SOURCE_INPUT_DECLARATION_INVALID") from error
        typed_hash = canonical_content_hash(
            {"contract": "PortfolioFinancialSourceCutInput:v1", "selection": row.declaration}
        )
        if (
            graph.portfolio_id != row.portfolio_id
            or typed_hash != row.content_hash
            or (previous is not None and row.portfolio_id <= previous)
        ):
            raise SourceManifestRejected("SOURCE_INPUT_TYPED_ORDER_DRIFT")
        root.append(typed_hash)
        if graph.compatibility is not None:
            result["compatibility_declaration_count"] = (
                result.get("compatibility_declaration_count", 0) + 1
            )
        previous = row.portfolio_id
    result.update(
        ordered_root_checkpoint=list(root.checkpoint), last_verified_portfolio_id=previous
    )
    if root.count > manifest.selection_count:
        raise SourceManifestRejected("SOURCE_INPUT_EXCESS_POPULATION")
    if not has_more:
        if root.finish() != (manifest.selection_count, manifest.selections_root):
            raise SourceManifestRejected("SOURCE_INPUT_POPULATION_MISMATCH")
        result.update(stage="SPAWN_CAPTURES", ordered_root_checkpoint=None, spawned_chunks=0)
    return result
