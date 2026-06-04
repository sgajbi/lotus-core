from portfolio_common.health_server import (
    HEALTH_PROBE_BIND_HOST_ENV,
    health_probe_bind_host,
)


def test_health_probe_bind_host_defaults_to_container_probe_host(monkeypatch) -> None:
    monkeypatch.delenv(HEALTH_PROBE_BIND_HOST_ENV, raising=False)

    assert health_probe_bind_host() == "0.0.0.0"


def test_health_probe_bind_host_uses_trimmed_environment_override(monkeypatch) -> None:
    monkeypatch.setenv(HEALTH_PROBE_BIND_HOST_ENV, " 127.0.0.1 ")

    assert health_probe_bind_host() == "127.0.0.1"
