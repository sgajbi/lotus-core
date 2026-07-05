from datetime import UTC
from uuid import UUID

from portfolio_common.runtime_providers import (
    SystemClock,
    SystemMonotonicTimer,
    UuidIdGenerator,
)


def test_system_clock_returns_aware_utc_timestamp() -> None:
    now = SystemClock().utc_now()

    assert now.tzinfo is UTC


def test_uuid_id_generator_returns_string_and_hex_ids() -> None:
    generator = UuidIdGenerator()

    assert str(UUID(generator.new_id()))
    assert len(generator.new_hex()) == 32


def test_system_monotonic_timer_returns_float_seconds() -> None:
    assert isinstance(SystemMonotonicTimer().seconds(), float)
