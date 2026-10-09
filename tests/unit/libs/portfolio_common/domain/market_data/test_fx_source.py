"""Synthetic FX source controls; no production provider or database qualification."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from portfolio_common.domain.market_data.fx_source import (
    MAX_FX_CUT_MEMBERS,
    FxSourceCut,
    FxSourceRevision,
    FxSourceScope,
    RetainedFxSourceCut,
    fx_cut_membership_hash,
)

pytestmark = [pytest.mark.unit, pytest.mark.domain, pytest.mark.contract]
OBSERVED = datetime(2026, 10, 8, 16, tzinfo=UTC)
SCOPE = FxSourceScope("SYNTHETIC_TENANT", "SYNTHETIC_PROVIDER", "SYNTHETIC_FEED")


def revision(record: str = "USD-SGD-CLOSE") -> FxSourceRevision:
    return FxSourceRevision(
        scope=SCOPE,
        source_record_id=record,
        source_revision="1",
        from_currency="USD",
        to_currency="SGD",
        rate_date=date(2026, 10, 8),
        rate=Decimal("1.3500000000"),
        source_observed_at=OBSERVED,
        fixing_kind="CLOSE",
        calendar_version="SYNTHETIC_CALENDAR_V1",
    )


def cut(members: tuple[FxSourceRevision, ...] | None = None) -> FxSourceCut:
    members = (revision(),) if members is None else members
    return FxSourceCut(
        scope=SCOPE,
        source_cut_reference="CLOSE-2026-10-08",
        source_cut_revision="1",
        source_observed_cutoff=OBSERVED,
        revisions=members,
        declared_member_count=len(members),
        declared_membership_hash=fx_cut_membership_hash(members),
    )


@pytest.mark.parametrize("field", ["tenant_id", "provider_id", "source_id"])
def test_revision_and_cut_identity_bind_every_namespace(field: str) -> None:
    changed_scope = replace(SCOPE, **{field: "SYNTHETIC_OTHER"})
    changed_revision = replace(revision(), scope=changed_scope)
    changed_cut = replace(
        cut(),
        scope=changed_scope,
        revisions=(changed_revision,),
        declared_membership_hash=fx_cut_membership_hash((changed_revision,)),
    )
    assert changed_revision.revision_id != revision().revision_id
    assert changed_cut.cut_id != cut().cut_id


def test_same_version_different_rate_retains_identity_but_changes_content() -> None:
    changed = replace(revision(), rate=Decimal("1.36"))
    assert changed.revision_id == revision().revision_id
    assert changed.content_hash != revision().content_hash
    assert cut((changed,)).cut_id == cut().cut_id
    assert cut((changed,)).content_hash != cut().content_hash


def test_equivalent_exact_decimal_representation_has_same_content() -> None:
    assert replace(revision(), rate=Decimal("1.35")).content_hash == revision().content_hash


def test_sealed_membership_is_order_independent_but_value_sensitive() -> None:
    first, second = revision("USD-SGD"), revision("USD-SGD-SECOND")
    assert cut((first, second)).content_hash == cut((second, first)).content_hash
    changed = replace(second, rate=Decimal("1.40"))
    with pytest.raises(ValueError, match="CONTENT_MISMATCH"):
        replace(cut((first, second)), revisions=(first, changed))


@pytest.mark.parametrize("count", [0, 2, True])
def test_exact_declared_count_is_required(count: object) -> None:
    with pytest.raises(ValueError, match="COUNT_MISMATCH"):
        replace(cut(), declared_member_count=count)


def test_missing_member_cannot_be_sealed_as_complete() -> None:
    original = cut((revision("FIRST"), revision("SECOND")))
    with pytest.raises(ValueError, match="COUNT_MISMATCH"):
        replace(original, revisions=original.revisions[:1])


@pytest.mark.parametrize("size", [0, MAX_FX_CUT_MEMBERS + 1])
def test_empty_or_oversized_cut_refuses(size: int) -> None:
    with pytest.raises(ValueError, match="SIZE_INVALID"):
        cut(tuple(revision(str(index)) for index in range(size)))


def test_exact_bounded_cut_size_accepts() -> None:
    value = cut(tuple(revision(str(index)) for index in range(MAX_FX_CUT_MEMBERS)))
    assert value.declared_member_count == MAX_FX_CUT_MEMBERS


def test_duplicate_record_and_wrong_scope_refuse() -> None:
    with pytest.raises(ValueError, match="DUPLICATE_RECORD"):
        cut((revision(), replace(revision(), source_revision="2")))
    with pytest.raises(ValueError, match="SCOPE_MISMATCH"):
        cut((replace(revision(), scope=replace(SCOPE, tenant_id="OTHER")),))


def test_source_cutoff_and_historical_knowledge_are_independent() -> None:
    retained = RetainedFxSourceCut(cut(), OBSERVED + timedelta(days=2))
    assert not retained.visible_at(source_as_of=OBSERVED, known_as_of=OBSERVED)
    assert not retained.visible_at(
        source_as_of=OBSERVED - timedelta(microseconds=1), known_as_of=retained.accepted_at
    )
    assert retained.visible_at(source_as_of=OBSERVED, known_as_of=retained.accepted_at)


def test_later_correction_does_not_mutate_retained_membership() -> None:
    retained = RetainedFxSourceCut(cut(), OBSERVED)
    original_hash = retained.cut.content_hash
    corrected = replace(
        revision(),
        source_revision="2",
        rate=Decimal("1.36"),
        predecessor_revision_id=revision().revision_id,
    )
    successor = replace(cut((corrected,)), source_cut_revision="2")
    assert successor.cut_id != retained.cut.cut_id
    assert retained.cut.content_hash == original_hash
    assert retained.cut.revisions[0].rate == Decimal("1.35")
    with pytest.raises(FrozenInstanceError):
        retained.accepted_at = OBSERVED + timedelta(days=1)


@pytest.mark.parametrize("rate", ["0", "-1", "NaN", "Infinity", "1e100000", "0.00000000001"])
def test_invalid_or_unrepresentable_rate_refuses_before_decimal_expansion(rate: str) -> None:
    with pytest.raises(ValueError):
        replace(revision(), rate=Decimal(rate))


def test_naive_future_and_self_predecessor_refuse() -> None:
    with pytest.raises(ValueError, match="INSTANT_INVALID"):
        replace(revision(), source_observed_at=OBSERVED.replace(tzinfo=None))
    with pytest.raises(ValueError, match="OBSERVATION_AFTER_CUTOFF"):
        cut((replace(revision(), source_observed_at=OBSERVED + timedelta(seconds=1)),))
    with pytest.raises(ValueError, match="OBSERVATION_AFTER_ACCEPTANCE"):
        RetainedFxSourceCut(cut(), OBSERVED - timedelta(seconds=1))
    with pytest.raises(ValueError, match="SELF_PREDECESSOR"):
        replace(revision(), predecessor_revision_id=revision().revision_id)


@pytest.mark.parametrize("value", ["", " trimmed", "a" * 129, "bad\nidentifier"])
def test_invalid_namespace_refuses(value: str) -> None:
    with pytest.raises(ValueError, match="IDENTIFIER_INVALID"):
        replace(SCOPE, source_id=value)
