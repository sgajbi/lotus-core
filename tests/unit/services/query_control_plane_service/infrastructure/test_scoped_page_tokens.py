"""Tests for route-scoped signed continuation tokens."""

import pytest
from portfolio_common.page_tokens import PageTokenCodec

from services.query_control_plane_service.app.infrastructure.scoped_page_tokens import (
    RouteScopedPageTokenCodec,
)


def test_route_scoped_codec_round_trips_payload() -> None:
    codec = RouteScopedPageTokenCodec(
        codec=PageTokenCodec(secret="test-secret"),
        route="integration.benchmark_market_series",
    )

    token = codec.encode({"last_index_id": "IDX_1"})

    assert codec.decode(token) == {"last_index_id": "IDX_1"}


def test_route_scoped_codec_rejects_cross_route_replay() -> None:
    shared = PageTokenCodec(secret="test-secret")
    benchmark_tokens = RouteScopedPageTokenCodec(
        codec=shared,
        route="integration.benchmark_market_series",
    )
    other_route_tokens = RouteScopedPageTokenCodec(
        codec=shared,
        route="integration.index_catalog",
    )

    token = benchmark_tokens.encode({"last_index_id": "IDX_1"})

    with pytest.raises(ValueError, match="route mismatch"):
        other_route_tokens.decode(token)
