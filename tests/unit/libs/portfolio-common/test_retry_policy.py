from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from portfolio_common.retry_policy import (
    RetryPolicyProfile,
    tenacity_retry_kwargs,
)
from tenacity import retry


class RetryableTestError(RuntimeError):
    pass


class NonRetryableTestError(RuntimeError):
    pass


def _test_profile() -> RetryPolicyProfile:
    return RetryPolicyProfile(
        name="test_retry_profile",
        max_attempts=3,
        max_elapsed_seconds=10.0,
        initial_backoff_seconds=0.0,
        max_backoff_seconds=0.0,
        reason="test_retry",
    )


def test_retry_policy_uses_bounded_exponential_jitter() -> None:
    kwargs = tenacity_retry_kwargs(
        profile=RetryPolicyProfile(
            name="jitter_profile",
            max_attempts=4,
            max_elapsed_seconds=12.0,
            initial_backoff_seconds=0.25,
            max_backoff_seconds=3.0,
            reason="jitter_retry",
        ),
        retry_exceptions=(RetryableTestError,),
        logger=logging.getLogger("test.retry"),
    )

    wait = kwargs["wait"]
    assert type(wait).__name__ == "wait_random_exponential"
    assert wait.__dict__["multiplier"] == 0.25
    assert wait.__dict__["max"] == 3.0


def test_retry_policy_retries_retryable_exception_until_budget_exhausted() -> None:
    attempts = 0

    @retry(
        **tenacity_retry_kwargs(
            profile=_test_profile(),
            retry_exceptions=(RetryableTestError,),
            logger=logging.getLogger("test.retry"),
        )
    )
    def always_retryable() -> None:
        nonlocal attempts
        attempts += 1
        raise RetryableTestError("retry me")

    with patch("portfolio_common.retry_policy.observe_retry_policy_event") as observe:
        with pytest.raises(RetryableTestError, match="retry me"):
            always_retryable()

    assert attempts == 3
    assert observe.call_count == 2
    observe.assert_called_with(
        profile="test_retry_profile",
        outcome="retrying",
        reason="test_retry",
    )


def test_retry_policy_does_not_retry_non_retryable_exception() -> None:
    attempts = 0

    @retry(
        **tenacity_retry_kwargs(
            profile=_test_profile(),
            retry_exceptions=(RetryableTestError,),
            logger=logging.getLogger("test.retry"),
        )
    )
    def non_retryable() -> None:
        nonlocal attempts
        attempts += 1
        raise NonRetryableTestError("do not retry")

    with patch("portfolio_common.retry_policy.observe_retry_policy_event") as observe:
        with pytest.raises(NonRetryableTestError, match="do not retry"):
            non_retryable()

    assert attempts == 1
    observe.assert_not_called()


def test_retry_policy_can_succeed_after_retryable_exception() -> None:
    attempts = 0

    @retry(
        **tenacity_retry_kwargs(
            profile=_test_profile(),
            retry_exceptions=(RetryableTestError,),
            logger=logging.getLogger("test.retry"),
        )
    )
    def succeeds_after_retry() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryableTestError("transient")
        return "ok"

    with patch("portfolio_common.retry_policy.observe_retry_policy_event") as observe:
        assert succeeds_after_retry() == "ok"

    assert attempts == 2
    observe.assert_called_once_with(
        profile="test_retry_profile",
        outcome="retrying",
        reason="test_retry",
    )
