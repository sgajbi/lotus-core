"""Append-only persistence boundary for authoritative market-price source facts."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from portfolio_common.database_models import MarketPriceSourceFactRecord
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactError,
    MarketPriceSourceFactStatus,
    OverlappingMarketPriceSourceFactError,
    ValuationAuthorityScope,
)
from portfolio_common.domain.valuation.source_versions import latest_source_versions
from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

AuthorityKey = tuple[str, str, str, date]
SourceKey = tuple[str, str]
SourceVersionKey = tuple[str, str, int]
MAX_MARKET_PRICE_SOURCE_FACT_WRITE_BATCH = 500
MARKET_PRICE_SOURCE_FACT_QUERY_CHUNK_SIZE = 100
_Value = TypeVar("_Value")


@dataclass(frozen=True, slots=True)
class MarketPriceAuthorityChange:
    """Old and accepted latest facts whose authorities require invalidation."""

    previous: MarketPriceSourceFact | None
    accepted: MarketPriceSourceFact

    @property
    def affected_authorities(self) -> frozenset[AuthorityKey]:
        authorities = {_authority_key(self.accepted)}
        if self.previous is not None:
            authorities.add(_authority_key(self.previous))
        return frozenset(authorities)


class MarketPriceSourceFactWriter:
    """Serialize corrections and append only unambiguous newer source versions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def append_many(
        self,
        facts: Sequence[MarketPriceSourceFact],
    ) -> tuple[MarketPriceAuthorityChange, ...]:
        """Append facts and return old/new authority impact without committing."""

        if not facts:
            return ()
        if len(facts) > MAX_MARKET_PRICE_SOURCE_FACT_WRITE_BATCH:
            raise MarketPriceSourceFactError(
                "market-price source-fact write batch exceeds "
                f"{MAX_MARKET_PRICE_SOURCE_FACT_WRITE_BATCH}"
            )
        _reject_duplicate_source_versions(facts)

        incoming_sources = sorted({fact.source_record_key for fact in facts})
        await self._lock_sources(incoming_sources)
        incoming_history = await self._load_histories(incoming_sources)
        persisted_by_version = {_source_version_key(fact): fact for fact in incoming_history}
        pending: list[MarketPriceSourceFact] = []
        for fact in facts:
            persisted = persisted_by_version.get(_source_version_key(fact))
            if persisted is not None:
                if persisted != fact:
                    raise MarketPriceSourceFactError(
                        "conflicting payloads share one source record and fact_version"
                    )
                continue
            pending.append(fact)
        if not pending:
            return ()

        previous_by_source = {fact.source_record_key: fact for fact in _latest(incoming_history)}
        pending.sort(key=lambda fact: (*fact.source_record_key, fact.fact_version))
        changes: list[MarketPriceAuthorityChange] = []
        latest_before_change = dict(previous_by_source)
        for fact in pending:
            previous = latest_before_change.get(fact.source_record_key)
            if previous is not None and fact.fact_version <= previous.fact_version:
                raise MarketPriceSourceFactError(
                    "market-price correction version must be newer than existing source history"
                )
            changes.append(MarketPriceAuthorityChange(previous=previous, accepted=fact))
            latest_before_change[fact.source_record_key] = fact

        affected_facts = list(pending)
        for fact in pending:
            previous = previous_by_source.get(fact.source_record_key)
            if previous is not None:
                affected_facts.append(previous)
        affected_authorities = sorted({_authority_key(fact) for fact in affected_facts})
        await self._lock_authorities(affected_authorities)

        candidate_sources = await self._candidate_sources(affected_authorities)
        all_candidate_sources = sorted(set(candidate_sources) | set(incoming_sources))
        durable_candidates = await self._load_histories(all_candidate_sources)
        _validate_no_active_authority_overlap([*durable_candidates, *pending])

        self._db.add_all([_record_from_fact(fact) for fact in pending])
        await self._db.flush()
        return tuple(changes)

    async def _lock_sources(self, sources: Sequence[SourceKey]) -> None:
        for source_system, source_record_id in sources:
            await self._db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": (f"market-price-source:{source_system}:{source_record_id}")},
            )

    async def _lock_authorities(self, authorities: Sequence[AuthorityKey]) -> None:
        for tenant_id, legal_book_id, security_id, price_date in authorities:
            await self._db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {
                    "lock_key": (
                        "market-price-authority:"
                        f"{tenant_id}:{legal_book_id}:{security_id}:{price_date}"
                    )
                },
            )

    async def _candidate_sources(
        self,
        authorities: Sequence[AuthorityKey],
    ) -> list[SourceKey]:
        record = MarketPriceSourceFactRecord
        sources: set[SourceKey] = set()
        for authority_chunk in _chunks(
            list(authorities),
            MARKET_PRICE_SOURCE_FACT_QUERY_CHUNK_SIZE,
        ):
            rows = (
                await self._db.execute(
                    select(record.source_system, record.source_record_id)
                    .where(
                        tuple_(
                            record.tenant_id,
                            record.legal_book_id,
                            record.security_id,
                            record.price_date,
                        ).in_(authority_chunk)
                    )
                    .distinct()
                )
            ).all()
            sources.update(
                (source_system, source_record_id) for source_system, source_record_id in rows
            )
        return sorted(sources)

    async def _load_histories(
        self,
        sources: Sequence[SourceKey],
    ) -> list[MarketPriceSourceFact]:
        record = MarketPriceSourceFactRecord
        facts: list[MarketPriceSourceFact] = []
        for source_chunk in _chunks(
            list(sources),
            MARKET_PRICE_SOURCE_FACT_QUERY_CHUNK_SIZE,
        ):
            rows = (
                await self._db.scalars(
                    select(record).where(
                        tuple_(record.source_system, record.source_record_id).in_(source_chunk)
                    )
                )
            ).all()
            facts.extend(_fact_from_record(row) for row in rows)
        return facts


def _chunks(values: list[_Value], size: int) -> list[list[_Value]]:
    return [values[offset : offset + size] for offset in range(0, len(values), size)]


def _reject_duplicate_source_versions(facts: Sequence[MarketPriceSourceFact]) -> None:
    identities = [_source_version_key(fact) for fact in facts]
    if len(identities) != len(set(identities)):
        raise MarketPriceSourceFactError(
            "market-price source-fact batch contains duplicate source versions"
        )


def _validate_no_active_authority_overlap(
    facts: Iterable[MarketPriceSourceFact],
) -> None:
    active_by_authority: dict[AuthorityKey, list[MarketPriceSourceFact]] = {}
    for fact in _latest(facts):
        if fact.fact_status is MarketPriceSourceFactStatus.ACTIVE:
            active_by_authority.setdefault(_authority_key(fact), []).append(fact)
    overlaps = {
        authority: authority_facts
        for authority, authority_facts in active_by_authority.items()
        if len(authority_facts) > 1
    }
    if overlaps:
        raise OverlappingMarketPriceSourceFactError(
            "multiple active market-price source records claim one exact authority"
        )


def _latest(facts: Iterable[MarketPriceSourceFact]) -> list[MarketPriceSourceFact]:
    latest: list[MarketPriceSourceFact] = latest_source_versions(
        facts,
        source_record_key=lambda fact: fact.source_record_key,
        source_version=lambda fact: fact.fact_version,
        conflicting_version_error=lambda: MarketPriceSourceFactError(
            "conflicting payloads share one source record and fact_version"
        ),
    )
    return latest


def _source_version_key(fact: MarketPriceSourceFact) -> SourceVersionKey:
    return (*fact.source_record_key, fact.fact_version)


def _authority_key(fact: MarketPriceSourceFact) -> AuthorityKey:
    return (*fact.scope.key, fact.price_date)


def _record_from_fact(fact: MarketPriceSourceFact) -> MarketPriceSourceFactRecord:
    return MarketPriceSourceFactRecord(
        tenant_id=fact.scope.tenant_id,
        legal_book_id=fact.scope.legal_book_id,
        security_id=fact.scope.security_id,
        price_date=fact.price_date,
        price=fact.price,
        currency=fact.currency,
        quote_basis=fact.quote_basis.value,
        fact_status=fact.fact_status.value,
        fact_version=fact.fact_version,
        source_system=fact.source_reference.source_system,
        source_record_id=fact.source_reference.source_record_id,
        source_revision=fact.source_reference.source_revision,
        source_content_hash=fact.source_reference.source_content_hash,
        observed_at=fact.source_reference.observed_at,
    )


def _fact_from_record(record: MarketPriceSourceFactRecord) -> MarketPriceSourceFact:
    return MarketPriceSourceFact(
        scope=ValuationAuthorityScope(
            tenant_id=record.tenant_id,
            legal_book_id=record.legal_book_id,
            security_id=record.security_id,
        ),
        price_date=record.price_date,
        price=record.price,
        currency=record.currency,
        quote_basis=MarketPriceQuoteBasis(record.quote_basis),
        source_reference=FinancialSourceReference(
            source_system=record.source_system,
            source_record_id=record.source_record_id,
            source_revision=record.source_revision,
            source_content_hash=record.source_content_hash,
            observed_at=record.observed_at,
        ),
        fact_status=MarketPriceSourceFactStatus(record.fact_status),
        fact_version=record.fact_version,
    )
