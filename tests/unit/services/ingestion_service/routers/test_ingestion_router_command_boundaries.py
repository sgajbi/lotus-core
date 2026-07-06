from pathlib import Path


PUBLISH_BACKED_ROUTERS = [
    "transactions.py",
    "portfolios.py",
    "instruments.py",
    "market_prices.py",
    "fx_rates.py",
    "portfolio_bundle.py",
    "reprocessing.py",
]


def _router_source(filename: str) -> str:
    return Path(f"src/services/ingestion_service/app/routers/{filename}").read_text(
        encoding="utf-8"
    )


def test_publish_backed_ingestion_routers_delegate_lifecycle_to_command_handler() -> None:
    forbidden_fragments = [
        "create_ingestion_job_id",
        "get_request_lineage",
        "enforce_ingestion_write_rate_limit",
        "mark_job_queued_after_publish_or_raise",
        "create_or_get_job(",
        "mark_failed(",
        "publish_transactions(",
        "publish_portfolios(",
        "publish_instruments(",
        "publish_market_prices(",
        "publish_fx_rates(",
        "publish_portfolio_bundle(",
        "publish_reprocessing_requests(",
    ]

    for filename in PUBLISH_BACKED_ROUTERS:
        source = _router_source(filename)
        assert "IngestionPublishCommandHandler" in source
        for fragment in forbidden_fragments:
            assert fragment not in source, f"{filename} reintroduced router orchestration"


def test_reference_data_router_delegates_persist_lifecycle_to_command_handler() -> None:
    source = _router_source("reference_data.py")

    assert "ReferenceDataIngestionCommandHandler" in source
    for fragment in [
        "create_ingestion_job_id",
        "get_request_lineage",
        "enforce_ingestion_write_rate_limit",
        "mark_job_queued_after_publish_or_raise",
        "create_or_get_job(",
        "mark_failed(",
        ".persist(",
    ]:
        assert fragment not in source
