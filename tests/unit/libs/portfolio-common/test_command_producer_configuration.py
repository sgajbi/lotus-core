"""Purpose enrollment defaults deny; previous keys cannot become implicit signers."""

import json

import pytest
from portfolio_common.command_authorization import (
    CommandAuthorizationRejected,
    load_command_authorization_policy,
)


def settings(**changes):
    return {
        "issuer": "qualified-issuer",
        "key_id": "current",
        "principal": "qualified-service",
        "secret_env": "LOTUS_SOURCE_CORRECTION_KEY_TEST",
        "signing_enabled": True,
    } | changes


def configure(monkeypatch, registry):
    monkeypatch.setenv("LOTUS_SOURCE_CORRECTION_PRODUCER_ENROLLMENTS", json.dumps(registry))
    monkeypatch.setenv(
        "LOTUS_SOURCE_CORRECTION_KEY_TEST", "synthetic-enrollment-key-material-123456789"
    )


def test_default_deny_has_no_signing_key(monkeypatch):
    monkeypatch.delenv("LOTUS_SOURCE_CORRECTION_PRODUCER_ENROLLMENTS", raising=False)
    assert load_command_authorization_policy().enrollments == ()


def test_active_and_previous_are_explicit_and_secrets_not_in_repr(monkeypatch):
    configure(monkeypatch, [settings(), settings(key_id="previous", signing_enabled=False)])
    policy = load_command_authorization_policy()
    assert [key.signing_enabled for key in policy.enrollments] == [True, False]
    assert "synthetic-enrollment" not in repr(policy)


@pytest.mark.parametrize(
    "registry",
    [
        [settings(), settings(key_id="ambiguous")],
        [settings(), settings()],
        [settings(secret="raw-secret-not-allowed")],
        [settings(secret_env="UNRELATED_ENV")],
        [settings(capability="ingestion.transactions.write")],
        [settings(signing_enabled="true")],
        [settings(issuer=" ")],
        [settings()] * 17,
        {"incorrect": "shape"},
    ],
)
def test_invalid_registry_is_bounded_closed_refusal(monkeypatch, registry):
    configure(monkeypatch, registry)
    with pytest.raises(CommandAuthorizationRejected) as error:
        load_command_authorization_policy()
    assert str(error.value) == "COMMAND_PRODUCER_CONFIGURATION_INVALID"


@pytest.mark.parametrize("secret", ["", "short"])
def test_missing_or_weak_key_refuses_without_disclosure(monkeypatch, secret):
    configure(monkeypatch, [settings()])
    monkeypatch.setenv("LOTUS_SOURCE_CORRECTION_KEY_TEST", secret)
    with pytest.raises(
        CommandAuthorizationRejected, match="^COMMAND_PRODUCER_CONFIGURATION_INVALID$"
    ):
        load_command_authorization_policy()


@pytest.mark.parametrize(
    "raw", ["not-json", "[" + " " * 32768 + "]"], ids=["invalid-json", "oversized"]
)
def test_invalid_json_or_oversized_config_refuses(monkeypatch, raw):
    if len(raw) > 32767:
        # Windows rejects an oversized environment entry before the loader.
        # Inject only the loader's environment read to exercise its own bound.
        from portfolio_common import command_authorization

        native_env_str = command_authorization.env_str
        monkeypatch.setattr(
            command_authorization,
            "env_str",
            lambda name, default=None: (
                raw
                if name == "LOTUS_SOURCE_CORRECTION_PRODUCER_ENROLLMENTS"
                else native_env_str(name, default)
            ),
        )
    else:
        monkeypatch.setenv("LOTUS_SOURCE_CORRECTION_PRODUCER_ENROLLMENTS", raw)
    with pytest.raises(
        CommandAuthorizationRejected, match="^COMMAND_PRODUCER_CONFIGURATION_INVALID$"
    ):
        load_command_authorization_policy()
