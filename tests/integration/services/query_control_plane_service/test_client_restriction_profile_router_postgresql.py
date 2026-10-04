"""Persisted restriction authority and legacy qualification on the registered QCP route."""

from datetime import UTC, date, datetime

import httpx
import pytest
from portfolio_common.database_models import (
    ClientRestrictionProfile,
    Portfolio,
    PortfolioMandateBinding,
)
from portfolio_common.db import get_async_db_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.DTOs.reference_data_client_restriction_dto import (
    ClientRestrictionProfileRecord,
)
from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)
from src.services.query_control_plane_service.app.main import app
from tests.test_support.tenant import TEST_LEGAL_BOOK_ID, TEST_TENANT_HEADERS, TEST_TENANT_ID

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]
PORTFOLIO = "RESTRICTION-AUTHORITY-PG"
CLIENT = "RESTRICTION-CLIENT-PG"
MANDATE = "RESTRICTION-MANDATE-PG"
ROUTE = f"/integration/portfolios/{PORTFOLIO}/client-restriction-profile"


def _record(code="LIFECYCLE", **overrides):
    payload = {
        "portfolio_id": PORTFOLIO,
        "client_id": CLIENT,
        "mandate_id": MANDATE,
        "restriction_scope": "instrument",
        "restriction_code": code,
        "restriction_status": "active",
        "restriction_source": "client_mandate",
        "instrument_ids": [" TARGET "],
        "effective_from": "2026-01-01",
        "restriction_version": 1,
        "source_record_id": f"{code}:1",
        "source_system": "restriction-proof",
        "observed_at": "2026-01-01T09:00:00Z",
    }
    payload.update(overrides)
    return ClientRestrictionProfileRecord.model_validate(payload)


async def _seed_identity(session):
    session.add(
        Portfolio(
            portfolio_id=PORTFOLIO,
            tenant_id=TEST_TENANT_ID,
            legal_book_id=TEST_LEGAL_BOOK_ID,
            base_currency="USD",
            open_date=date(2020, 1, 1),
            risk_exposure="MODERATE",
            investment_time_horizon="LONG_TERM",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id=CLIENT,
            status="ACTIVE",
            is_leverage_allowed=False,
        )
    )
    await session.flush()
    session.add(
        PortfolioMandateBinding(
            portfolio_id=PORTFOLIO,
            client_id=CLIENT,
            mandate_id=MANDATE,
            mandate_type="discretionary",
            discretionary_authority_status="active",
            booking_center_code="SG",
            jurisdiction_code="SG",
            model_portfolio_id="MODEL-PG",
            risk_profile="balanced",
            investment_horizon="long_term",
            rebalance_frequency="MONTHLY",
            rebalance_bands={},
            effective_from=date(2020, 1, 1),
            source_record_id="binding:1",
            source_system="restriction-proof",
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await session.commit()


async def _persist(session, *records):
    await ReferenceDataIngestionService(session).upsert_client_restriction_profiles(
        [record.model_dump(mode="python") for record in records]
    )
    session.expunge_all()


async def _query(client, as_of, *, inclusive=False, mandate=MANDATE):
    response = await client.post(
        ROUTE,
        json={
            "as_of_date": as_of,
            "tenant_id": TEST_TENANT_ID,
            "mandate_id": mandate,
            "include_inactive_restrictions": inclusive,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["client_id"] == CLIENT
    assert payload["mandate_id"] == MANDATE
    assert payload["tenant_id"] == TEST_TENANT_ID
    return payload


async def test_registered_profile_selects_authority_before_lifecycle_and_preserves_history(
    clean_db,
    async_db_session: AsyncSession,
):
    await _seed_identity(async_db_session)
    await _persist(
        async_db_session,
        _record(),
        _record(
            restriction_status="inactive",
            effective_from="2026-02-01",
            restriction_version=2,
            source_record_id="LIFECYCLE:2",
            observed_at="2026-02-01T09:00:00Z",
        ),
        _record(
            restriction_status="suspended",
            effective_from="2026-03-01",
            restriction_version=3,
            source_record_id="LIFECYCLE:3",
            observed_at="2026-03-01T09:00:00Z",
        ),
        _record(
            effective_from="2026-04-01",
            restriction_version=4,
            source_record_id="LIFECYCLE:4",
            observed_at="2026-04-01T09:00:00Z",
        ),
        # Same-date correction: later observation wins, while retained version/lineage identify it.
        _record(
            effective_from="2026-04-01",
            restriction_version=5,
            restriction_status="inactive",
            source_record_id="LIFECYCLE:5",
            observed_at="2026-04-01T10:00:00Z",
        ),
        _record(
            effective_from="2026-05-01",
            effective_to="2026-05-31",
            restriction_version=6,
            source_record_id="LIFECYCLE:6",
            observed_at="2026-05-01T09:00:00Z",
        ),
    )

    async def db_override():
        yield async_db_session

    previous = app.dependency_overrides.get(get_async_db_session)
    app.dependency_overrides[get_async_db_session] = db_override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers=TEST_TENANT_HEADERS,
        ) as client:
            for as_of, version, lifecycle in (
                ("2026-01-31", 1, "active"),
                ("2026-02-01", 2, "inactive"),
                ("2026-03-01", 3, "suspended"),
                ("2026-04-01", 5, "inactive"),
                ("2026-04-30", 5, "inactive"),
                ("2026-05-01", 6, "active"),
                ("2026-05-31", 6, "active"),
                ("2026-06-01", 5, "inactive"),
            ):
                inclusive = await _query(client, as_of, inclusive=True)
                assert len(inclusive["restrictions"]) == 1
                entry = inclusive["restrictions"][0]
                assert (
                    entry["restriction_version"],
                    entry["restriction_status"],
                    entry["source_record_id"],
                ) == (version, lifecycle, f"LIFECYCLE:{version}")
                assert entry["instrument_ids"] == ["TARGET"]
                active = await _query(client, as_of)
                if lifecycle == "active":
                    assert active["restrictions"] == inclusive["restrictions"]
                    assert active["supportability"]["state"] == "READY"
                else:
                    assert active["restrictions"] == []
                    assert active["supportability"]["state"] == "INCOMPLETE"
                    assert active["supportability"]["reason"] == "CLIENT_RESTRICTION_PROFILE_EMPTY"
                    assert active["data_quality_status"] == "MISSING"
            # Independent codes, global and four selector families remain supported.
            await _persist(
                async_db_session,
                *[
                    _record(
                        scope.upper(),
                        restriction_scope=scope,
                        **{"instrument_ids": [], **selectors},
                    )
                    for scope, selectors in (
                        ("client", {"mandate_id": None}),
                        ("mandate", {}),
                        ("instrument", {"instrument_ids": ["TARGET"]}),
                        ("issuer", {"issuer_ids": ["ISSUER"]}),
                        ("country", {"country_codes": ["SG"]}),
                        ("asset_class", {"asset_classes": ["Equity"]}),
                    )
                ],
            )
            await _persist(
                async_db_session,
                _record("OTHER-MANDATE", mandate_id="OTHER"),
                _record("OTHER-CLIENT", client_id="OTHER"),
            )
            positive = await _query(client, "2026-04-02")
            assert {row["restriction_code"] for row in positive["restrictions"]} == {
                "CLIENT",
                "MANDATE",
                "INSTRUMENT",
                "ISSUER",
                "COUNTRY",
                "ASSET_CLASS",
            }
            assert positive["supportability"]["state"] == "READY"
            missing = await client.post(
                ROUTE,
                json={
                    "as_of_date": "2026-04-02",
                    "mandate_id": "OTHER",
                },
            )
            assert missing.status_code == 404
            # Retained legacy history bypasses current admission only to test read qualification.
            legacy = _record("LEGACY").model_dump(mode="python")
            legacy["instrument_ids"] = [" \t "]
            async_db_session.add(ClientRestrictionProfile(**legacy))
            await async_db_session.commit()
            async_db_session.expunge_all()
            blocked = await _query(client, "2026-04-02")
            assert blocked["supportability"]["state"] == "UNAVAILABLE"
            assert (
                blocked["supportability"]["reason"]
                == "CLIENT_RESTRICTION_PROFILE_INVALID_SELECTORS"
            )
            assert blocked["data_quality_status"] == "INVALID"
            legacy_entry = next(
                row for row in blocked["restrictions"] if row["restriction_code"] == "LEGACY"
            )
            assert legacy_entry["instrument_ids"] == [""]
            assert legacy_entry["source_record_id"] == "LEGACY:1"
            retained = (
                await async_db_session.execute(
                    select(ClientRestrictionProfile).where(
                        ClientRestrictionProfile.restriction_code == "LEGACY"
                    )
                )
            ).scalar_one()
            assert retained.instrument_ids == [" \t "]
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_async_db_session, None)
        else:
            app.dependency_overrides[get_async_db_session] = previous
