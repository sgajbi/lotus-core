from __future__ import annotations

import os

from portfolio_common.logging_utils import redact_sensitive_text


def should_verbose_test_output(env: dict[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    raw_value = source.get("LOTUS_TESTS_VERBOSE")
    if raw_value is None:
        return False
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def emit_test_output(message: str, *, verbose_only: bool = False) -> None:
    if verbose_only and not should_verbose_test_output():
        return
    print(redact_sensitive_text(message))
