from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN

from src.services.query_service.app.dtos.core_snapshot_dto import (
    CoreSnapshotFreshnessMetadata,
    CoreSnapshotMode,
    CoreSnapshotRequest,
    CoreSnapshotSection,
)
from src.services.query_service.app.services.core_snapshot_service import (
    CoreSnapshotBadRequestError,
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
    CoreSnapshotService,
    CoreSnapshotUnavailableSectionError,
    get_core_snapshot_service,
)

pytestmark = pytest.mark.asyncio


def _snapshot_row(
    security_id: str = "SEC_AAPL_US",
    quantity: Decimal = Decimal("10"),
    market_value: Decimal = Decimal("100"),
    market_value_local: Decimal = Decimal("100"),
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
):
    return SimpleNamespace(
        security_id=security_id,
        quantity=quantity,
        market_value=market_value,
        market_value_local=market_value_local,
        created_at=created_at,
        updated_at=updated_at,
    )


def _instrument(
    security_id: str = "SEC_AAPL_US",
    currency: str = "USD",
    asset_class: str = "EQUITY",
):
    return SimpleNamespace(
        security_id=security_id,
        name=f"{security_id}-name",
        isin=f"{security_id}-isin",
        currency=currency,
        asset_class=asset_class,
        sector="TECHNOLOGY",
        country_of_risk="US",
        issuer_id=f"ISSUER_{security_id}",
        issuer_name=f"{security_id} issuer",
        ultimate_parent_issuer_id=f"PARENT_{security_id}",
        ultimate_parent_issuer_name=f"{security_id} parent",
        liquidity_tier="L2",
    )


@pytest.fixture
def mock_dependencies():
    position_repo = AsyncMock()
    portfolio_repo = AsyncMock()
    simulation_repo = AsyncMock()
    price_repo = AsyncMock()
    fx_repo = AsyncMock()
    instrument_repo = AsyncMock()

    portfolio_repo.get_by_id.return_value = SimpleNamespace(
        portfolio_id="PORT_001",
        base_currency="USD",
    )
    position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
        (
            _snapshot_row(
                created_at=datetime(2026, 2, 27, 9, 30, tzinfo=UTC),
                updated_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
            ),
            _instrument(),
            SimpleNamespace(
                status="CURRENT",
                epoch=7,
                created_at=datetime(2026, 2, 27, 9, 0, tzinfo=UTC),
                updated_at=datetime(2026, 2, 27, 10, 5, tzinfo=UTC),
            ),
        )
    ]
    position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = []
    simulation_repo.get_session.return_value = SimpleNamespace(
        session_id="SIM_1",
        portfolio_id="PORT_001",
        version=3,
    )
    simulation_repo.get_changes.return_value = []
    fx_repo.get_fx_rates.return_value = [SimpleNamespace(rate=Decimal("1.1"))]
    price_repo.get_prices.return_value = [SimpleNamespace(price=Decimal("10"), currency="USD")]
    instrument_repo.get_by_security_ids.return_value = [_instrument("SEC_NEW_US")]

    with (
        patch(
            "src.services.query_service.app.services.core_snapshot_service.PositionRepository",
            return_value=position_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.PortfolioRepository",
            return_value=portfolio_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.SimulationRepository",
            return_value=simulation_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.MarketPriceRepository",
            return_value=price_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.FxRateRepository",
            return_value=fx_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.InstrumentRepository",
            return_value=instrument_repo,
        ),
    ):
        yield (
            position_repo,
            portfolio_repo,
            simulation_repo,
            price_repo,
            fx_repo,
            instrument_repo,
        )


async def test_core_snapshot_baseline_success(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[
            CoreSnapshotSection.POSITIONS_BASELINE,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
            CoreSnapshotSection.INSTRUMENT_ENRICHMENT,
        ],
    )

    response = await service.get_core_snapshot("PORT_001", request)

    assert response.portfolio_id == "PORT_001"
    assert response.sections.positions_baseline is not None
    assert len(response.sections.positions_baseline) == 1
    assert response.sections.portfolio_totals is not None
    assert response.sections.instrument_enrichment is not None
    assert response.sections.instrument_enrichment[0].issuer_id is not None
    assert response.sections.instrument_enrichment[0].issuer_name is not None
    assert response.sections.instrument_enrichment[0].ultimate_parent_issuer_id is not None
    assert response.sections.instrument_enrichment[0].ultimate_parent_issuer_name is not None
    assert response.sections.instrument_enrichment[0].liquidity_tier == "L2"
    assert response.contract_version == "rfc_081_v1"
    assert response.request_fingerprint
    assert response.freshness.baseline_source == "position_state"
    assert response.freshness.snapshot_epoch == 7
    assert response.freshness.snapshot_timestamp == datetime(2026, 2, 27, 10, 5, tzinfo=UTC)
    assert response.freshness.fallback_reason is None
    assert response.governance.consumer_system == "lotus-performance"
    assert response.governance.tenant_id == "default"
    assert response.governance.policy_provenance.policy_version == "snapshot.policy.inline.default"
    assert response.product_name == "PortfolioStateSnapshot"
    assert response.product_version == "v1"
    assert response.tenant_id == "default"
    assert response.restatement_version == "current"
    assert response.reconciliation_status == "UNKNOWN"
    assert response.data_quality_status == COMPLETE
    assert response.latest_evidence_timestamp == datetime(2026, 2, 27, 10, 5, tzinfo=UTC)
    assert response.source_batch_fingerprint is None
    assert response.snapshot_id is None
    assert response.policy_version == "snapshot.policy.inline.default"
    assert response.correlation_id is None


async def test_snapshot_data_quality_status_classifies_snapshot_evidence() -> None:
    assert (
        CoreSnapshotService._snapshot_data_quality_status(
            freshness=CoreSnapshotFreshnessMetadata(
                freshness_status="CURRENT_SNAPSHOT",
                baseline_source="position_state",
                snapshot_timestamp=datetime(2026, 2, 27, 10, 5, tzinfo=UTC),
                snapshot_epoch=7,
            ),
            baseline_count=1,
        )
        == COMPLETE
    )
    assert (
        CoreSnapshotService._snapshot_data_quality_status(
            freshness=CoreSnapshotFreshnessMetadata(
                freshness_status="CURRENT_SNAPSHOT",
                baseline_source="position_state",
                snapshot_timestamp=datetime(2026, 2, 27, 10, 5, tzinfo=UTC),
                snapshot_epoch=None,
            ),
            baseline_count=2,
        )
        == PARTIAL
    )
    assert (
        CoreSnapshotService._snapshot_data_quality_status(
            freshness=CoreSnapshotFreshnessMetadata(
                freshness_status="HISTORICAL_FALLBACK",
                baseline_source="position_history",
                fallback_reason="NO_CURRENT_POSITION_STATE_ROWS",
            ),
            baseline_count=1,
        )
        == PARTIAL
    )
    assert (
        CoreSnapshotService._snapshot_data_quality_status(
            freshness=CoreSnapshotFreshnessMetadata(
                freshness_status="HISTORICAL_FALLBACK",
                baseline_source="position_history",
                fallback_reason="NO_CURRENT_POSITION_STATE_ROWS",
            ),
            baseline_count=0,
        )
        == UNKNOWN
    )


async def test_get_instrument_enrichment_bulk_preserves_order_and_unknowns(mock_dependencies):
    (_, _, _, _, _, instrument_repo) = mock_dependencies
    instrument_repo.get_by_security_ids.return_value = [
        _instrument("SEC_MSFT_US"),
        _instrument("SEC_AAPL_US"),
    ]

    service = CoreSnapshotService(AsyncMock())
    records = await service.get_instrument_enrichment_bulk(
        ["SEC_AAPL_US", "SEC_UNKNOWN", "SEC_MSFT_US"]
    )

    assert [record.security_id for record in records] == [
        "SEC_AAPL_US",
        "SEC_UNKNOWN",
        "SEC_MSFT_US",
    ]
    assert records[0].issuer_id == "ISSUER_SEC_AAPL_US"
    assert records[0].liquidity_tier == "L2"
    assert records[1].issuer_id is None
    assert records[1].liquidity_tier is None
    assert records[2].issuer_id == "ISSUER_SEC_MSFT_US"
    assert records[2].liquidity_tier == "L2"


async def test_core_snapshot_simulation_success(mock_dependencies):
    (_, _, simulation_repo, _, _, _) = mock_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_AAPL_US",
            transaction_type="BUY",
            quantity=Decimal("5"),
            amount=None,
        )
    ]
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[
            CoreSnapshotSection.POSITIONS_BASELINE,
            CoreSnapshotSection.POSITIONS_PROJECTED,
            CoreSnapshotSection.POSITIONS_DELTA,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
        ],
        simulation={"session_id": "SIM_1", "expected_version": 3},
    )

    response = await service.get_core_snapshot("PORT_001", request)

    assert response.simulation is not None
    assert response.sections.positions_projected is not None
    assert response.sections.positions_delta is not None
    assert response.sections.positions_projected[0].quantity == Decimal("15")
    assert response.tenant_id == "default"
    assert response.policy_version == "snapshot.policy.inline.default"


async def test_core_snapshot_rejects_projected_sections_in_baseline_mode(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
    )

    with pytest.raises(CoreSnapshotBadRequestError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_portfolio_missing(mock_dependencies):
    (_, portfolio_repo, _, _, _, _) = mock_dependencies
    portfolio_repo.get_by_id.return_value = None
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
    )

    with pytest.raises(CoreSnapshotNotFoundError):
        await service.get_core_snapshot("PORT_404", request)


async def test_core_snapshot_raises_when_simulation_session_missing(mock_dependencies):
    (_, _, simulation_repo, _, _, _) = mock_dependencies
    simulation_repo.get_session.return_value = None
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_404"},
    )

    with pytest.raises(CoreSnapshotNotFoundError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_session_portfolio_mismatch(mock_dependencies):
    (_, _, simulation_repo, _, _, _) = mock_dependencies
    simulation_repo.get_session.return_value = SimpleNamespace(
        session_id="SIM_1",
        portfolio_id="PORT_X",
        version=3,
    )
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1"},
    )

    with pytest.raises(CoreSnapshotConflictError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_expected_version_mismatch(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1", "expected_version": 99},
    )

    with pytest.raises(CoreSnapshotConflictError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_fx_rate_missing(mock_dependencies):
    (_, portfolio_repo, _, _, fx_repo, _) = mock_dependencies
    portfolio_repo.get_by_id.return_value = SimpleNamespace(
        portfolio_id="PORT_001",
        base_currency="EUR",
    )
    fx_repo.get_fx_rates.return_value = []
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        reporting_currency="USD",
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
    )

    with pytest.raises(CoreSnapshotUnavailableSectionError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_new_security_has_no_instrument(mock_dependencies):
    (_, _, simulation_repo, _, _, instrument_repo) = mock_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_UNKNOWN",
            transaction_type="BUY",
            quantity=Decimal("2"),
            amount=None,
        )
    ]
    instrument_repo.get_by_security_ids.return_value = []
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1"},
    )

    with pytest.raises(CoreSnapshotUnavailableSectionError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_new_security_has_no_market_price(mock_dependencies):
    (_, _, simulation_repo, price_repo, _, _) = mock_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_NEW_US",
            transaction_type="BUY",
            quantity=Decimal("2"),
            amount=None,
        )
    ]
    price_repo.get_prices.return_value = []
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1"},
    )

    with pytest.raises(CoreSnapshotUnavailableSectionError):
        await service.get_core_snapshot("PORT_001", request)


@pytest.mark.parametrize(
    ("txn_type", "quantity", "amount", "expected"),
    [
        ("BUY", Decimal("2"), None, Decimal("2")),
        ("SELL", Decimal("2"), None, Decimal("-2")),
        ("TRANSFER_IN", Decimal("5"), Decimal("9"), Decimal("5")),
        ("TRANSFER_OUT", Decimal("3"), Decimal("9"), Decimal("-3")),
        ("DEPOSIT", None, Decimal("7"), Decimal("7")),
        ("WITHDRAWAL", None, Decimal("7"), Decimal("-7")),
        ("FEE", None, Decimal("7"), Decimal("-7")),
        ("TAX", None, Decimal("7"), Decimal("-7")),
        ("UNKNOWN", Decimal("3"), None, Decimal("0")),
    ],
)
async def test_change_quantity_effect_rules(txn_type, quantity, amount, expected):
    change = SimpleNamespace(transaction_type=txn_type, quantity=quantity, amount=amount)
    assert CoreSnapshotService._change_quantity_effect(change) == expected


async def test_get_fx_rate_or_raise_identity_currency(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())
    rate = await service._get_fx_rate_or_raise("USD", "USD", date(2026, 2, 27))
    assert rate == Decimal("1")


async def test_resolve_baseline_positions_uses_history_fallback(mock_dependencies):
    (position_repo, _, _, _, _, _) = mock_dependencies
    position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = []
    position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = [
        (
            SimpleNamespace(
                security_id="SEC_BOND_US",
                quantity=Decimal("3"),
                cost_basis=Decimal("45"),
                cost_basis_local=Decimal("45"),
                created_at=datetime(2026, 2, 27, 8, 30, tzinfo=UTC),
                updated_at=datetime(2026, 2, 27, 8, 45, tzinfo=UTC),
            ),
            _instrument("SEC_BOND_US", "USD", "BOND"),
            SimpleNamespace(
                status="CURRENT",
                updated_at=datetime(2026, 2, 27, 8, 50, tzinfo=UTC),
            ),
        )
    ]
    service = CoreSnapshotService(AsyncMock())
    rows, source = await service._resolve_baseline_positions(
        portfolio_id="PORT_001",
        as_of_date=date(2026, 2, 27),
        reporting_fx=Decimal("1"),
        include_cash=True,
        include_zero=True,
    )
    assert rows["SEC_BOND_US"]["market_value_base"] == Decimal("45")
    assert source.baseline_source == "position_history"
    assert source.freshness_status == "HISTORICAL_FALLBACK"
    assert source.snapshot_timestamp is None
    assert source.fallback_reason == "NO_CURRENT_POSITION_STATE_ROWS"


async def test_core_snapshot_history_fallback_classifies_data_quality_partial(mock_dependencies):
    (position_repo, _, _, _, _, _) = mock_dependencies
    position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = []
    position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = [
        (
            SimpleNamespace(
                security_id="SEC_BOND_US",
                quantity=Decimal("3"),
                cost_basis=Decimal("45"),
                cost_basis_local=Decimal("45"),
            ),
            _instrument("SEC_BOND_US", "USD", "BOND"),
            SimpleNamespace(status="CURRENT"),
        )
    ]
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
    )

    response = await service.get_core_snapshot("PORT_001", request)

    assert response.freshness.freshness_status == "HISTORICAL_FALLBACK"
    assert response.data_quality_status == PARTIAL
    assert response.latest_evidence_timestamp is None


async def test_latest_snapshot_timestamp_uses_latest_row_or_state_timestamp():
    latest = CoreSnapshotService._latest_snapshot_timestamp(
        [
            (
                _snapshot_row(
                    created_at=datetime(2026, 2, 27, 9, 30, tzinfo=UTC),
                    updated_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
                ),
                _instrument(),
                SimpleNamespace(updated_at=datetime(2026, 2, 27, 10, 5, tzinfo=UTC)),
            )
        ]
    )

    assert latest == datetime(2026, 2, 27, 10, 5, tzinfo=UTC)


async def test_resolve_baseline_positions_leaves_snapshot_epoch_null_for_mixed_epochs(
    mock_dependencies,
):
    (position_repo, _, _, _, _, _) = mock_dependencies
    position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
        (
            _snapshot_row("SEC_A", Decimal("1"), Decimal("10"), Decimal("10")),
            _instrument("SEC_A"),
            SimpleNamespace(status="CURRENT", epoch=7),
        ),
        (
            _snapshot_row("SEC_B", Decimal("2"), Decimal("20"), Decimal("20")),
            _instrument("SEC_B"),
            SimpleNamespace(status="CURRENT", epoch=8),
        ),
    ]
    service = CoreSnapshotService(AsyncMock())

    _rows, freshness = await service._resolve_baseline_positions(
        portfolio_id="PORT_001",
        as_of_date=date(2026, 2, 27),
        reporting_fx=Decimal("1"),
        include_cash=True,
        include_zero=True,
    )

    assert freshness.baseline_source == "position_state"
    assert freshness.snapshot_epoch is None


async def test_resolve_baseline_positions_applies_cash_and_zero_filters(mock_dependencies):
    (position_repo, _, _, _, _, _) = mock_dependencies
    position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
        (
            _snapshot_row("SEC_CASH", Decimal("1"), Decimal("1"), Decimal("1")),
            _instrument("SEC_CASH", "USD", "CASH"),
            SimpleNamespace(status="CURRENT"),
        ),
        (
            _snapshot_row("SEC_ZERO", Decimal("0"), Decimal("0"), Decimal("0")),
            _instrument("SEC_ZERO", "USD", "EQUITY"),
            SimpleNamespace(status="CURRENT"),
        ),
    ]
    service = CoreSnapshotService(AsyncMock())
    rows, _source = await service._resolve_baseline_positions(
        portfolio_id="PORT_001",
        as_of_date=date(2026, 2, 27),
        reporting_fx=Decimal("1"),
        include_cash=False,
        include_zero=False,
    )
    assert rows == {}


async def test_resolve_projected_positions_handles_non_positive_quantity_branch(mock_dependencies):
    (_, _, simulation_repo, _, _, instrument_repo) = mock_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_NEG",
            transaction_type="SELL",
            quantity=Decimal("1"),
            amount=None,
        )
    ]
    instrument_repo.get_by_security_ids.return_value = [_instrument("SEC_NEG")]
    service = CoreSnapshotService(AsyncMock())
    projected = await service._resolve_projected_positions(
        session_id="SIM_1",
        as_of_date=date(2026, 2, 27),
        portfolio_base_currency="USD",
        reporting_currency="USD",
        baseline_positions={},
        include_zero=True,
        include_cash=True,
    )
    assert projected["SEC_NEG"]["market_value_base"] == Decimal("0")


async def test_resolve_projected_positions_prices_new_security_with_fx(mock_dependencies):
    (_, _, simulation_repo, price_repo, fx_repo, instrument_repo) = mock_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_NEW_EUR",
            transaction_type="BUY",
            quantity=Decimal("2"),
            amount=None,
        )
    ]
    instrument_repo.get_by_security_ids.return_value = [_instrument("SEC_NEW_EUR", "EUR", "EQUITY")]
    price_repo.get_prices.return_value = [SimpleNamespace(price=Decimal("10"), currency="EUR")]
    fx_repo.get_fx_rates.side_effect = [
        [SimpleNamespace(rate=Decimal("1.2"))],  # EUR -> USD portfolio
        [SimpleNamespace(rate=Decimal("1.5"))],  # USD -> SGD reporting
    ]
    service = CoreSnapshotService(AsyncMock())

    projected = await service._resolve_projected_positions(
        session_id="SIM_1",
        as_of_date=date(2026, 2, 27),
        portfolio_base_currency="USD",
        reporting_currency="SGD",
        baseline_positions={},
        include_zero=True,
        include_cash=True,
    )

    assert projected["SEC_NEW_EUR"]["market_value_local"] == Decimal("20")
    assert projected["SEC_NEW_EUR"]["market_value_base"] == Decimal("36")


async def test_resolve_projected_positions_filters_cash_and_zero_quantity(mock_dependencies):
    (_, _, simulation_repo, _, _, _) = mock_dependencies
    simulation_repo.get_changes.return_value = []
    service = CoreSnapshotService(AsyncMock())

    projected = await service._resolve_projected_positions(
        session_id="SIM_1",
        as_of_date=date(2026, 2, 27),
        portfolio_base_currency="USD",
        reporting_currency="USD",
        baseline_positions={
            "SEC_CASH": {
                "security_id": "SEC_CASH",
                "quantity": Decimal("1"),
                "baseline_quantity": Decimal("1"),
                "market_value_base": Decimal("1"),
                "market_value_local": Decimal("1"),
                "currency": "USD",
                "instrument_name": "Cash",
                "asset_class": "CASH",
                "sector": None,
                "country_of_risk": None,
                "isin": None,
                "issuer_id": None,
                "issuer_name": None,
                "ultimate_parent_issuer_id": None,
                "ultimate_parent_issuer_name": None,
            },
            "SEC_ZERO": {
                "security_id": "SEC_ZERO",
                "quantity": Decimal("0"),
                "baseline_quantity": Decimal("0"),
                "market_value_base": Decimal("0"),
                "market_value_local": Decimal("0"),
                "currency": "USD",
                "instrument_name": "Zero",
                "asset_class": "EQUITY",
                "sector": None,
                "country_of_risk": None,
                "isin": None,
                "issuer_id": None,
                "issuer_name": None,
                "ultimate_parent_issuer_id": None,
                "ultimate_parent_issuer_name": None,
            },
        },
        include_zero=False,
        include_cash=False,
    )

    assert projected == {}


async def test_get_instrument_enrichment_bulk_rejects_empty_request(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())

    with pytest.raises(
        CoreSnapshotBadRequestError,
        match="security_ids must contain at least one identifier",
    ):
        await service.get_instrument_enrichment_bulk(["", "  "])


async def test_static_helpers_cover_zero_total_and_delta_paths():
    items = {
        "SEC_1": {
            "security_id": "SEC_1",
            "quantity": Decimal("1"),
            "market_value_base": Decimal("0"),
            "market_value_local": Decimal("0"),
            "currency": "USD",
        }
    }
    CoreSnapshotService._assign_baseline_weights(items, Decimal("0"))
    CoreSnapshotService._assign_projected_weights(items, Decimal("0"))
    assert items["SEC_1"]["position_record"].weight == Decimal("0")

    baseline_total = CoreSnapshotService._total_market_value_baseline(items)
    projected_total = CoreSnapshotService._total_market_value_projected(items)
    assert baseline_total == Decimal("0")
    assert projected_total == Decimal("0")

    delta_rows = CoreSnapshotService._build_delta_section(
        baseline_positions=items,
        projected_positions={},
        baseline_total=Decimal("0"),
        projected_total=Decimal("0"),
    )
    assert delta_rows[0].delta_quantity == Decimal("-1")


async def test_get_core_snapshot_service_factory_returns_service():
    service = get_core_snapshot_service(db=AsyncMock())
    assert isinstance(service, CoreSnapshotService)


async def test_core_snapshot_request_fingerprint_is_deterministic(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
        consumer_system="lotus-performance",
        tenant_id="tenant_sg_pb",
    )

    first = await service.get_core_snapshot("PORT_001", request)
    second = await service.get_core_snapshot("PORT_001", request)

    assert first.request_fingerprint == second.request_fingerprint
    assert first.governance.consumer_system == "lotus-performance"
    assert first.governance.tenant_id == "tenant_sg_pb"
