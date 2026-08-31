"""SQL adapter tests for DPM readiness reference evidence."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.services.query_control_plane_service.app.contracts.model_portfolio_targets import (
    MODEL_PORTFOLIO_TARGET_MAX_COUNT,
)
from src.services.query_control_plane_service.app.infrastructure.dpm_reference_data_sources import (
    SqlAlchemyDpmReferenceDataReader,
)


def _session_returning(*rows: object) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    result.scalars.return_value.first.return_value = rows[0] if rows else None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _timestamps() -> dict[str, datetime]:
    return {
        "observed_at": datetime(2026, 4, 10, 8, tzinfo=UTC),
        "created_at": datetime(2026, 4, 10, 9, tzinfo=UTC),
        "updated_at": datetime(2026, 4, 10, 10, tzinfo=UTC),
    }


@pytest.mark.asyncio
async def test_model_targets_use_effective_rank_and_map_decimal_evidence() -> None:
    row = SimpleNamespace(
        instrument_id="BOND_001",
        target_weight="0.6000000000",
        min_weight="0.5000000000",
        max_weight="0.7000000000",
        target_status="active",
        effective_from=date(2026, 4, 1),
        effective_to=None,
        source_system="model_office",
        source_record_id="target:1",
        quality_status="accepted",
        **_timestamps(),
    )
    session = _session_returning(row)

    result = await SqlAlchemyDpmReferenceDataReader(session).list_model_portfolio_targets(
        model_portfolio_id="MODEL_1",
        model_portfolio_version="2026.04",
        as_of_date=date(2026, 4, 10),
        include_inactive_targets=False,
    )

    assert str(result.records[0].target_weight) == "0.6000000000"
    assert result.limit_exceeded is False
    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert "row_number() OVER" in sql
    assert "model_portfolio_targets.target_status" in sql
    assert "ORDER BY model_portfolio_targets.instrument_id ASC" in sql
    assert statement._limit_clause.value == MODEL_PORTFOLIO_TARGET_MAX_COUNT + 1


@pytest.mark.asyncio
async def test_model_target_reader_discards_ceiling_sentinel_on_source_overflow() -> None:
    session = _session_returning(
        *[
            SimpleNamespace(instrument_id=f"SEC_{index:04d}")
            for index in range(MODEL_PORTFOLIO_TARGET_MAX_COUNT + 1)
        ]
    )

    result = await SqlAlchemyDpmReferenceDataReader(session).list_model_portfolio_targets(
        model_portfolio_id="MODEL_1",
        model_portfolio_version="2026.04",
        as_of_date=date(2026, 4, 10),
        include_inactive_targets=False,
    )

    assert result.limit_exceeded is True
    assert result.records == ()


@pytest.mark.asyncio
async def test_mandate_binding_applies_requested_disambiguators() -> None:
    row = SimpleNamespace(
        portfolio_id="PB_1",
        mandate_id="MANDATE_1",
        client_id="CLIENT_1",
        mandate_type="discretionary",
        discretionary_authority_status="active",
        booking_center_code="Singapore",
        jurisdiction_code="SG",
        model_portfolio_id="MODEL_1",
        policy_pack_id="POLICY_1",
        mandate_objective="balanced growth",
        risk_profile="balanced",
        investment_horizon="long_term",
        review_cadence="quarterly",
        last_review_date=date(2026, 3, 31),
        next_review_due_date=date(2026, 6, 30),
        leverage_allowed=False,
        tax_awareness_allowed=True,
        settlement_awareness_required=True,
        rebalance_frequency="monthly",
        rebalance_bands={"default_band": "0.025"},
        effective_from=date(2026, 4, 1),
        effective_to=None,
        binding_version=2,
        source_system="mandate_admin",
        source_record_id="mandate:1",
        quality_status="accepted",
        **_timestamps(),
    )
    session = _session_returning(row)

    evidence = await SqlAlchemyDpmReferenceDataReader(
        session
    ).resolve_discretionary_mandate_binding(
        tenant_id="tenant-test",
        portfolio_id="PB_1",
        as_of_date=date(2026, 4, 10),
        mandate_id="MANDATE_1",
        booking_center_code="Singapore",
    )

    assert evidence is not None
    assert evidence.rebalance_bands == {"default_band": "0.025"}
    sql = str(session.execute.await_args.args[0])
    assert "JOIN portfolios" in sql
    assert "portfolios.tenant_id" in sql
    assert "portfolio_mandate_bindings.mandate_id" in sql
    assert "portfolio_mandate_bindings.booking_center_code" in sql


@pytest.mark.asyncio
async def test_latest_market_prices_normalize_ids_and_bound_as_of_date() -> None:
    session = _session_returning(
        SimpleNamespace(
            security_id=" SEC_1 ",
            price_date=date(2026, 4, 9),
            price="101.1234567890",
            currency="SGD",
            created_at=_timestamps()["created_at"],
            updated_at=_timestamps()["updated_at"],
        )
    )

    records = await SqlAlchemyDpmReferenceDataReader(session).list_latest_market_prices(
        security_ids=[" SEC_1 ", "SEC_1"],
        as_of_date=date(2026, 4, 10),
    )

    assert records[0].security_id == "SEC_1"
    assert str(records[0].price) == "101.1234567890"
    sql = str(session.execute.await_args.args[0])
    assert "max(market_prices.price_date)" in sql
    assert "market_prices.price_date <=" in sql


@pytest.mark.asyncio
async def test_eligibility_reader_chunks_oversized_inputs_and_globally_orders_results() -> None:
    later_record = SimpleNamespace(
        security_id="SEC_1000",
        eligibility_status="approved",
        product_shelf_status="approved",
        buy_allowed=True,
        sell_allowed=True,
        restriction_reason_codes=[],
        settlement_days=2,
        settlement_calendar_id="GLOBAL",
        liquidity_tier=None,
        issuer_id=None,
        issuer_name=None,
        ultimate_parent_issuer_id=None,
        ultimate_parent_issuer_name=None,
        asset_class="Equity",
        country_of_risk="US",
        effective_from=date(2026, 4, 1),
        effective_to=None,
        eligibility_version=1,
        source_system="eligibility",
        source_record_id="eligibility:1000",
        quality_status="accepted",
        **_timestamps(),
    )
    earlier_record = SimpleNamespace(
        **{**vars(later_record), "security_id": "SEC_0000", "source_record_id": "eligibility:0"}
    )
    first_result = MagicMock()
    first_result.scalars.return_value.all.return_value = [later_record]
    second_result = MagicMock()
    second_result.scalars.return_value.all.return_value = [earlier_record]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[first_result, second_result])

    records = await SqlAlchemyDpmReferenceDataReader(session).list_instrument_eligibility_profiles(
        security_ids=[f"SEC_{index:04d}" for index in reversed(range(1_001))],
        as_of_date=date(2026, 4, 10),
    )

    assert [record.security_id for record in records] == ["SEC_0000", "SEC_1000"]
    assert session.execute.await_count == 2
    first_statement = session.execute.await_args_list[0].args[0]
    compiled = first_statement.compile(dialect=postgresql.dialect())
    expanding_values = next(value for value in compiled.params.values() if isinstance(value, list))
    assert expanding_values == [f"SEC_{index:04d}" for index in range(1_000)]


@pytest.mark.asyncio
async def test_latest_fx_rates_normalize_and_deduplicate_pairs() -> None:
    session = _session_returning(
        SimpleNamespace(
            from_currency=" usd ",
            to_currency="sgd",
            rate_date=date(2026, 4, 10),
            rate="1.3500000000",
            created_at=_timestamps()["created_at"],
            updated_at=_timestamps()["updated_at"],
        )
    )

    records = await SqlAlchemyDpmReferenceDataReader(session).list_latest_fx_rates(
        currency_pairs=[("usd", "sgd"), (" USD ", "SGD")],
        as_of_date=date(2026, 4, 10),
    )

    assert (records[0].from_currency, records[0].to_currency) == ("USD", "SGD")
    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert "max(fx_rates.rate_date)" in sql
    assert "fx_rates.rate_date <=" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "argument_name", "values"),
    [
        (
            "list_latest_market_prices",
            "security_ids",
            [f"SEC_{index:04d}" for index in range(1_001)],
        ),
        (
            "list_latest_fx_rates",
            "currency_pairs",
            [
                (
                    "".join(
                        (
                            chr(65 + (index // (26 * 26)) % 26),
                            chr(65 + (index // 26) % 26),
                            chr(65 + index % 26),
                        )
                    ),
                    "ZZZ",
                )
                for index in range(1_001)
            ],
        ),
    ],
)
async def test_market_data_readers_chunk_oversized_internal_inputs(
    method_name: str,
    argument_name: str,
    values: list[object],
) -> None:
    session = _session_returning()
    reader = SqlAlchemyDpmReferenceDataReader(session)

    await getattr(reader, method_name)(**{argument_name: values, "as_of_date": date(2026, 4, 10)})

    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_market_price_reader_globally_orders_populated_chunk_results() -> None:
    later_record = SimpleNamespace(
        security_id="SEC_1000",
        price_date=date(2026, 4, 10),
        price="102.0000000000",
        currency="SGD",
        created_at=_timestamps()["created_at"],
        updated_at=_timestamps()["updated_at"],
    )
    earlier_record = SimpleNamespace(
        security_id="SEC_0000",
        price_date=date(2026, 4, 10),
        price="101.0000000000",
        currency="SGD",
        created_at=_timestamps()["created_at"],
        updated_at=_timestamps()["updated_at"],
    )
    first_result = MagicMock()
    first_result.scalars.return_value.all.return_value = [later_record]
    second_result = MagicMock()
    second_result.scalars.return_value.all.return_value = [earlier_record]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[first_result, second_result])

    records = await SqlAlchemyDpmReferenceDataReader(session).list_latest_market_prices(
        security_ids=[f"SEC_{index:04d}" for index in range(1_001)],
        as_of_date=date(2026, 4, 10),
    )

    assert [record.security_id for record in records] == ["SEC_0000", "SEC_1000"]
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_market_data_readers_sort_normalized_inputs_before_chunking() -> None:
    session = _session_returning()
    reader = SqlAlchemyDpmReferenceDataReader(session)

    await reader.list_latest_market_prices(
        security_ids=[" SEC_2 ", "SEC_1", "SEC_2"],
        as_of_date=date(2026, 4, 10),
    )

    compiled = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    expanding_values = next(value for value in compiled.params.values() if isinstance(value, list))
    assert expanding_values == ["SEC_1", "SEC_2"]
