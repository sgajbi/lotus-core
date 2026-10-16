"""Neutral declarations preserve unknowns and hash semantics without certifying authority."""

from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest
from portfolio_common.domain.portfolio_financial_source_cuts import (
    CompatibilityDeclaration,
    DeclaredCoverage,
    EffectiveDeclaration,
    ExpectedPopulation,
    FinancialSourceCut,
    HistoricalRegistryCut,
    HistoricalRegistryMember,
    InputRole,
    ProductSelection,
    SettledUnencumberedDeclaration,
    SourceCutIdentity,
    ordered_content_root,
    source_product_bytes,
)

pytestmark = [pytest.mark.unit, pytest.mark.domain]
H = "a" * 64


def identity():
    return SourceCutIdentity(
        "tenant",
        "producer",
        "registry",
        "cut",
        1,
        "v1",
        date(2025, 1, 1),
        date(2025, 1, 31),
        "SG-business",
        datetime(2025, 2, 1, tzinfo=UTC),
        datetime(2025, 2, 2, tzinfo=UTC),
        None,
        None,
    )


def declaration(**changes):
    return replace(
        EffectiveDeclaration(
            date(2025, 1, 1), None, "mandate-v1", "issued-declaration", "USD", None, True
        ),
        **changes,
    )


def member(**changes):
    return replace(
        HistoricalRegistryMember("member", "provider", None, 1, (declaration(),)), **changes
    )


def financial():
    selections = tuple(
        ProductSelection(
            role,
            "PortfolioTimeseriesInput"
            if role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS)
            else "PortfolioFinancialFlowObservations"
            if role is InputRole.FLOWS
            else "PortfolioFinancialSourceObservations",
            "v1",
            H,
            H,
            "receipt",
            "revision",
        )
        for role in InputRole
    )
    return FinancialSourceCut(
        identity(),
        "portfolio",
        "USD",
        date(2024, 12, 31),
        date(2025, 1, 31),
        H,
        1,
        selections,
        None,
        None,
    )


def test_false_unknown_and_true_are_distinct_retained_members():
    members = [
        member(declarations=(declaration(discretionary=value),)) for value in (None, False, True)
    ]
    assert len({m.content_hash for m in members}) == 3
    assert members[0].core_portfolio_id is None
    assert member(declarations=(declaration(included=False),)).content_hash != member().content_hash


@pytest.mark.parametrize("value", [0, 1, "false", "true", [], {}])
def test_discretionary_never_coerces(value):
    with pytest.raises(ValueError):
        declaration(discretionary=value)


def test_half_open_adjacent_currency_and_termination_history():
    first = declaration(effective_to=date(2025, 2, 1))
    second = declaration(effective_from=date(2025, 2, 1), currency="SGD", included=False)
    assert member(declarations=(first, second)).declarations[-1].included is False
    with pytest.raises(ValueError):
        member(declarations=(first, declaration(effective_from=date(2025, 1, 31))))
    with pytest.raises(ValueError):
        member(declarations=(second, first))


def test_revision_cas_and_aware_source_times():
    corrected = replace(identity(), revision=2, predecessor_hash=H, expected_head_hash=H)
    assert corrected.revision == 2
    for changes in (
        {"revision": True},
        {"revision": 2},
        {"predecessor_hash": H},
        {"revision": 2, "predecessor_hash": H, "expected_head_hash": "b" * 64},
        {"observed_at": datetime(2025, 2, 1)},
    ):
        with pytest.raises(ValueError):
            replace(identity(), **changes)


def test_complete_empty_is_retained_without_population_authority():
    _, empty = ordered_content_root("PortfolioHistoricalRegistryMembers:v1", ())
    cut = HistoricalRegistryCut(
        identity(),
        ExpectedPopulation("independent", "v1", 0, H),
        DeclaredCoverage.COMPLETE,
        0,
        empty,
        0,
        empty,
    )
    assert cut.population_verification == "UNVERIFIED"
    assert cut.content_hash != replace(cut, declared_coverage=DeclaredCoverage.MISSING).content_hash
    assert (
        cut.content_hash
        != replace(cut, expected_population=ExpectedPopulation("other", "v1", 5, H)).content_hash
    )


def test_compatibility_requires_declaration_bound_to_exact_five_roots():
    cut = financial()
    assert cut.compatibility_posture == "UNAVAILABLE"
    declaration = CompatibilityDeclaration(
        "producer",
        "registry",
        "v1",
        H,
        tuple((s.role, s.content_hash) for s in cut.selections),
        date(2025, 1, 1),
        date(2025, 1, 31),
        "USD",
        "declared-basis",
        H,
    )
    assert replace(cut, compatibility=declaration).compatibility_posture == "DECLARED_UNVERIFIED"
    with pytest.raises(ValueError):
        replace(cut, compatibility=replace(declaration, registry_root="b" * 64))
    with pytest.raises(ValueError):
        replace(cut, selections=cut.selections[:-1])
    with pytest.raises(ValueError):
        replace(cut.selections[0], product_name="PortfolioFinancialSourceObservations")


@pytest.mark.parametrize(
    "amount",
    [1.2, "1.2", Decimal("NaN"), Decimal("Infinity"), Decimal("1e-16384"), Decimal("1e131072")],
)
def test_cash_declaration_refuses_lossy_or_unrepresentable_amounts(amount):
    with pytest.raises((ValueError, TypeError)):
        SettledUnencumberedDeclaration(
            amount, "USD", date(2025, 1, 31), "explicit-settled-unencumbered", "revision"
        )


def test_cash_zero_unknown_and_exact_value_are_independent_under_hostile_precision():
    with localcontext() as context:
        context.prec = 2
        values = [
            SettledUnencumberedDeclaration(amount, "USD", date(2025, 1, 31), "declared", "r1")
            for amount in (None, Decimal(0), Decimal("50.123456789"))
        ]
        hashes = {replace(financial(), settled_unencumbered=value).content_hash for value in values}
    assert len(hashes) == 3
    assert values[-1].amount == Decimal("50.123456789")


def test_streamed_roots_preserve_order_count_and_contract():
    assert ordered_content_root("members-v1", (H for _ in range(1001)))[0] == 1001
    assert ordered_content_root("members-v1", [H, "b" * 64]) != ordered_content_root(
        "members-v1", ["b" * 64, H]
    )
    assert ordered_content_root("members-v1", []) != ordered_content_root("members-v2", [])


def test_acquired_dto_bytes_have_versioned_serializer_and_not_supplier_wire_claim():
    first = source_product_bytes({"value": "0", "missing": None}, serializer="qcp-source-json:v1")
    assert first == source_product_bytes(
        {"missing": None, "value": "0"}, serializer="qcp-source-json:v1"
    )
    assert first != source_product_bytes(
        {"value": "0", "missing": None}, serializer="qcp-source-json:v2"
    )
    with pytest.raises(ValueError):
        source_product_bytes({"value": float("nan")}, serializer="qcp-source-json:v1")


def test_duck_or_subclass_declarations_cannot_supply_arbitrary_authority_or_mutable_cash():
    cut = financial()
    compatibility = CompatibilityDeclaration(
        "producer",
        "registry",
        "v1",
        H,
        tuple((s.role, s.content_hash) for s in cut.selections),
        date(2025, 1, 1),
        date(2025, 1, 31),
        "USD",
        "declared-basis",
        H,
    )
    duck = SimpleNamespace(**asdict(compatibility), posture="QUALIFIED")
    with pytest.raises(ValueError, match="governed compatibility"):
        replace(cut, compatibility=duck)
    mutable_cash = SimpleNamespace(
        currency="USD", business_date=cut.month_end_date, amount=Decimal(0)
    )
    with pytest.raises(ValueError, match="governed settled-unencumbered"):
        replace(cut, settled_unencumbered=mutable_cash)

    class UncheckedCompatibility(CompatibilityDeclaration):
        @property
        def posture(self):
            return "QUALIFIED"

    subclass = UncheckedCompatibility(**asdict(compatibility))
    with pytest.raises(ValueError, match="governed compatibility"):
        replace(cut, compatibility=subclass)
    valid = replace(cut, compatibility=compatibility)
    assert valid.compatibility_posture == "DECLARED_UNVERIFIED"
    assert cut.compatibility_posture == "UNAVAILABLE"


def test_exact_declaration_instances_are_semantically_revalidated_before_admission():
    cut = financial()
    cash = SettledUnencumberedDeclaration(Decimal(0), "USD", cut.month_end_date, "explicit", "r1")
    assert replace(cut, settled_unencumbered=cash).settled_unencumbered.amount == 0
    object.__setattr__(cash, "amount", 1.2)
    with pytest.raises((ValueError, TypeError)):
        replace(cut, settled_unencumbered=cash)
    compatibility = CompatibilityDeclaration(
        "producer",
        "registry",
        "v1",
        H,
        tuple((s.role, s.content_hash) for s in cut.selections),
        date(2025, 1, 1),
        date(2025, 1, 31),
        "USD",
        "declared-basis",
        H,
    )
    object.__setattr__(
        compatibility, "role_roots", tuple(list(pair) for pair in compatibility.role_roots)
    )
    with pytest.raises(ValueError, match="five-role"):
        replace(cut, compatibility=compatibility)
