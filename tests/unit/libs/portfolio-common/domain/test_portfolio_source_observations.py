"""Immutable independent facts, exact amounts and source-safe correction refusals."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationConflict,
    ObservationCoverage,
    ObservationEnvelope,
    require_observation_hash,
    require_successor,
)

pytestmark = [pytest.mark.unit, pytest.mark.domain]


def test_persistence_metadata_has_scoped_heads_receipts_and_independent_exact_amounts():
    from portfolio_common import database_models  # Register native referenced tables.
    from portfolio_common.financial_numeric import ExactNumeric
    from portfolio_common.portfolio_source_observation_models import (
        SOURCE_IDENTITY_COLUMNS,
        CashAvailabilityObservationHead,
        CashAvailabilityObservationRow,
        FundingInvestmentObservationHead,
        FundingInvestmentObservationRow,
    )
    from sqlalchemy.dialects.postgresql import dialect
    from sqlalchemy.schema import CreateTable

    assert database_models.Portfolio.__table__.name == "portfolios"
    for fact, head in (
        (CashAvailabilityObservationRow, CashAvailabilityObservationHead),
        (FundingInvestmentObservationRow, FundingInvestmentObservationHead),
    ):
        fact_sql = str(CreateTable(fact.__table__).compile(dialect=dialect()))
        head_sql = str(CreateTable(head.__table__).compile(dialect=dialect()))
        assert "qualification = 'unqualified'" in fact_sql
        assert "REFERENCES ingestion_jobs (tenant_id, job_id)" in fact_sql
        assert "REFERENCES portfolios (tenant_id, portfolio_id)" in fact_sql
        assert "predecessor_id, expected_head_hash" in fact_sql
        assert "effective_to > effective_from" in fact_sql
        assert (
            tuple(column.name for column in head.__table__.primary_key) == SOURCE_IDENTITY_COLUMNS
        )
        assert (
            "tenant_id, portfolio_id, producer_id, source_record_id, observation_id, content_hash"
            in head_sql
        )
    for name in ("settled_amount", "encumbered_amount", "available_amount"):
        column = CashAvailabilityObservationRow.__table__.c[name]
        assert isinstance(column.type, ExactNumeric)
        assert column.type.precision is None and column.type.scale is None
        assert column.nullable
    assert "NaN" in str(
        CreateTable(CashAvailabilityObservationRow.__table__).compile(dialect=dialect())
    )
    assert not set(("settled_amount", "available_amount")) & set(
        FundingInvestmentObservationRow.__table__.c.keys()
    )


def _envelope(**changes) -> ObservationEnvelope:
    return replace(
        ObservationEnvelope(
            "TENANT_SYNTHETIC",
            "PORTFOLIO_SYNTHETIC",
            "producer-synthetic",
            "source-cash",
            1,
            "cash-cut-original",
            "cash-definition-v1",
            date(2026, 1, 1),
            date(2026, 2, 1),
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            ObservationCoverage.COMPLETE,
            "all-declared-accounts",
        ),
        **changes,
    )


def _cash(**changes) -> CashAvailabilityObservation:
    return replace(
        CashAvailabilityObservation(_envelope(), "SGD", Decimal("100"), None, Decimal("0")),
        **changes,
    )


def test_zero_unknown_and_negative_supplied_available_are_not_a_formula() -> None:
    observation = _cash()
    assert observation.settled == Decimal("100")
    assert observation.encumbered is None and observation.available == Decimal("0")
    assert replace(observation, available=None).content_hash != observation.content_hash
    assert replace(observation, available=Decimal("-2")).available == Decimal("-2")


@pytest.mark.parametrize("field", ["settled", "encumbered", "available"])
@pytest.mark.parametrize(
    "source,expected",
    [
        ("-0", "0"),
        ("-0.00", "0.00"),
        ("1E+3", "1000"),
        ("0E+3", "0"),
        ("-1E+3", "-1000"),
        ("0.00", "0.00"),
        (
            "123456789012345678901234.1234567890123456789000",
            "123456789012345678901234.1234567890123456789000",
        ),
        (
            "-123456789012345678901234.1234567890123456789000",
            "-123456789012345678901234.1234567890123456789000",
        ),
    ],
)
def test_cash_numeric_identity_is_exact_under_low_precision_context(field, source, expected):
    supplied = Decimal(source)
    before = supplied.as_tuple()
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = context.traps[Rounded] = True
        fact = _cash(**{field: supplied})
        equivalent = _cash(**{field: Decimal(expected)})
        assert getattr(fact, field).as_tuple() == Decimal(expected).as_tuple()
        assert fact.content_hash == equivalent.content_hash
    assert supplied.as_tuple() == before


def test_cash_canonicalization_keeps_fractional_display_scale_unknown_and_shared_hash():
    from portfolio_common.domain.calculation_lineage import canonical_content_hash

    assert (
        _cash(available=Decimal("-0.00")).content_hash
        == _cash(available=Decimal("0.00")).content_hash
    )
    assert (
        _cash(available=Decimal("0.00")).content_hash != _cash(available=Decimal("0")).content_hash
    )
    assert _cash(available=None).available is None
    assert canonical_content_hash({"amount": Decimal("-0")}) != canonical_content_hash(
        {"amount": Decimal("0")}
    )


def test_business_visibility_uses_half_open_effective_interval_not_observed_date() -> None:
    envelope = _envelope(
        observed_at=datetime(2026, 2, 3, tzinfo=UTC), generated_at=datetime(2026, 2, 4, tzinfo=UTC)
    )
    assert envelope.is_effective(date(2026, 1, 1))
    assert not envelope.is_effective(date(2025, 12, 31))
    assert not envelope.is_effective(date(2026, 2, 1))


def test_original_and_corrected_hashes_are_independent_and_original_frozen() -> None:
    original = _cash()
    original_hash = original.content_hash
    correction = replace(
        original,
        available=Decimal("20"),
        envelope=_envelope(
            source_revision=2,
            predecessor_id="original-observation",
            expected_head_hash=original_hash,
            source_cut_id="cash-cut-corrected",
        ),
    )
    require_successor(original, correction, original_id="original-observation")
    assert original.content_hash == original_hash != correction.content_hash
    with pytest.raises(FrozenInstanceError):
        original.available = Decimal("20")


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "OTHER_TENANT"),
        ("portfolio_id", "OTHER_PORTFOLIO"),
        ("producer_id", "other-producer"),
        ("source_record_id", "other-source"),
    ],
)
def test_correction_refuses_foreign_source_owner(field, value) -> None:
    original = _cash()
    correction = replace(
        original,
        envelope=_envelope(
            source_revision=2,
            predecessor_id="original",
            expected_head_hash=original.content_hash,
            **{field: value},
        ),
    )
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_OWNER_MISMATCH"):
        require_successor(original, correction, original_id="original")


@pytest.mark.parametrize(
    "changes",
    [
        {"predecessor_id": "wrong"},
        {"expected_head_hash": "a" * 64},
        {"source_revision": 3},
    ],
)
def test_correction_refuses_stale_head(changes) -> None:
    original = _cash()
    values = dict(
        source_revision=2, predecessor_id="original", expected_head_hash=original.content_hash
    )
    values.update(changes)
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_STALE_HEAD"):
        require_successor(
            original, replace(original, envelope=_envelope(**values)), original_id="original"
        )


@pytest.mark.parametrize(
    "value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), 1.25, True]
)
def test_cash_refuses_non_decimal_or_nonfinite(value) -> None:
    with pytest.raises(ValueError):
        _cash(available=value)


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": " tenant "},
        {"source_cut_id": ""},
        {"source_revision": True},
        {"source_revision": 2},
        {"effective_to": date(2026, 1, 1)},
        {"observed_at": datetime(2026, 1, 1)},
        {"generated_at": datetime(2025, 12, 31, tzinfo=UTC)},
        {"predecessor_id": "parent"},
        {"coverage": "accepted"},
    ],
)
def test_envelope_refuses_unbound_or_ambiguous_source(changes) -> None:
    with pytest.raises(ValueError):
        _envelope(**changes)


def test_hash_binds_family_scope_coverage_and_validates_tampering() -> None:
    observation = _cash()
    require_observation_hash(observation, observation.content_hash)
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_HASH_MISMATCH"):
        require_observation_hash(
            replace(observation, available=Decimal("1")), observation.content_hash
        )
    assert (
        replace(observation, envelope=_envelope(coverage=ObservationCoverage.PARTIAL)).content_hash
        != observation.content_hash
    )
    equivalent = replace(
        observation,
        envelope=_envelope(
            observed_at=datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
        ),
    )
    assert equivalent.content_hash == observation.content_hash


@pytest.mark.parametrize(
    "funded,invested", [(None, None), (True, False), (False, True), (False, False)]
)
def test_readiness_retains_independent_explicit_assertions(funded, invested) -> None:
    result = FundingInvestmentObservation(_envelope(), funded, invested)
    assert (result.funded, result.invested) == (funded, invested)
    assert result.content_hash != _cash().content_hash


@pytest.mark.parametrize("value", [0, 1, "true", Decimal("1")])
def test_readiness_refuses_coerced_flags(value) -> None:
    with pytest.raises(ValueError):
        FundingInvestmentObservation(_envelope(), value, None)


@pytest.mark.parametrize("currency", ["sgd", "S1D", "SG", "ＳＧＤ", None])
def test_cash_refuses_noncanonical_currency(currency) -> None:
    with pytest.raises(ValueError):
        _cash(currency=currency)


def test_correction_cannot_cross_fact_family() -> None:
    original = _cash()
    correction = FundingInvestmentObservation(
        _envelope(
            source_revision=2, predecessor_id="original", expected_head_hash=original.content_hash
        ),
        True,
        False,
    )
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_OWNER_MISMATCH"):
        require_successor(original, correction, original_id="original")


@pytest.mark.parametrize("dimension", ["coverage_scope", "currency"])
def test_correction_cannot_reassign_authority_scope(dimension) -> None:
    original = _cash()
    envelope = replace(
        original.envelope,
        source_revision=2,
        predecessor_id=original.content_hash,
        expected_head_hash=original.content_hash,
    )
    correction = replace(original, envelope=envelope)
    if dimension == "currency":
        correction = replace(correction, currency="USD")
    else:
        correction = replace(correction, envelope=replace(envelope, coverage_scope="other"))
    with pytest.raises(ObservationConflict, match="SOURCE_OBSERVATION_OWNER_MISMATCH"):
        require_successor(original, correction, original_id=original.content_hash)


@pytest.mark.parametrize("field", ["settled", "encumbered", "available"])
@pytest.mark.parametrize(
    "source",
    ["1E+999999999", "-1E+999999999", "1E-999999999", "-0E-999999999", "1E+131072", "1E-16384"],
)
def test_cash_refuses_compact_unrepresentable_exponents_before_expansion(field, source) -> None:
    class NoExpansionDecimal(Decimal):
        def __format__(self, spec):
            raise AssertionError("unrepresentable value must not be expanded")

    with pytest.raises(ValueError, match="PostgreSQL NUMERIC representation limits"):
        _cash(**{field: NoExpansionDecimal(source)})


@pytest.mark.parametrize("source", ["1E-7", "-1E-16383", "1E+131071", "-0E+999999999"])
def test_cash_retains_supported_numeric_limits_without_context_rounding(source) -> None:
    value = Decimal(source)
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        fact = _cash(settled=value)
    expected = (
        Decimal("0")
        if value.is_zero()
        else Decimal(format(value, "f"))
        if value.as_tuple().exponent > 0
        else value
    )
    assert fact.settled.as_tuple() == expected.as_tuple()


def test_successor_keeps_owner_but_may_change_independent_source_values() -> None:
    original = _cash()
    correction = replace(
        original,
        available=Decimal("-1.00"),
        envelope=replace(
            original.envelope,
            source_revision=2,
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
            source_cut_id="corrected-cut",
        ),
    )
    require_successor(original, correction, original_id=original.content_hash)
    assert correction.content_hash != original.content_hash
