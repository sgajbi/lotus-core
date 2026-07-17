from pathlib import Path

import pytest

from scripts.quality.structured_log_guard import evaluate_structured_log_guard


def test_structured_log_guard_rejects_f_string_messages(tmp_path: Path) -> None:
    source = tmp_path / "bad.py"
    source.write_text(
        "\n".join(
            [
                "import logging",
                "logger = logging.getLogger(__name__)",
                "def run(portfolio_id):",
                "    logger.info(f'Fetching portfolio {portfolio_id}')",
            ]
        ),
        encoding="utf-8",
    )

    errors = evaluate_structured_log_guard((source,))

    assert len(errors) == 1
    assert "logger message must not be an f-string" in errors[0]


def test_structured_log_guard_rejects_sensitive_format_args(tmp_path: Path) -> None:
    source = tmp_path / "bad.py"
    source.write_text(
        "\n".join(
            [
                "import logging",
                "logger = logging.getLogger(__name__)",
                "def run(portfolio_id):",
                "    logger.info('Fetching portfolio %s', portfolio_id)",
            ]
        ),
        encoding="utf-8",
    )

    errors = evaluate_structured_log_guard((source,))

    assert len(errors) == 1
    assert "sensitive identifier `portfolio_id`" in errors[0]


def test_structured_log_guard_accepts_constant_message_with_safe_extra(tmp_path: Path) -> None:
    source = tmp_path / "good.py"
    source.write_text(
        "\n".join(
            [
                "import logging",
                "logger = logging.getLogger(__name__)",
                "def run(row_count):",
                "    logger.info(",
                "        'Fetched portfolio rows.',",
                "        extra={",
                "            'event_name': 'portfolio.rows_fetched',",
                "            'operation': 'portfolio.list',",
                "            'status': 'succeeded',",
                "            'reason_code': 'rows_fetched',",
                "            'row_count': row_count,",
                "        },",
                "    )",
            ]
        ),
        encoding="utf-8",
    )

    assert evaluate_structured_log_guard((source,)) == []


@pytest.mark.parametrize(
    "message",
    [
        "Deleted stale position history records.",
        "Kafka message delivered.",
        "Outbox dispatcher flush completed.",
        "Outbox dispatcher marked events as processed.",
        "Position history replay lock acquired.",
        "Staged FX rate upsert.",
        "Staged instrument upsert.",
        "Staged market price upsert.",
        "Skipping cashflow creation for non-cash FX contract lifecycle event.",
        "Transaction processing completed.",
    ],
)
def test_structured_log_guard_rejects_high_volume_routine_info_event(
    tmp_path: Path,
    message: str,
) -> None:
    source = tmp_path / "hot_path.py"
    source.write_text(
        "\n".join(
            [
                "import logging",
                "logger = logging.getLogger(__name__)",
                "def process():",
                f"    logger.info({message!r})",
            ]
        ),
        encoding="utf-8",
    )

    errors = evaluate_structured_log_guard((source,))

    assert len(errors) == 1
    assert "high-volume routine event must use logger.debug" in errors[0]


def test_structured_log_guard_accepts_high_volume_routine_debug_event(tmp_path: Path) -> None:
    source = tmp_path / "hot_path.py"
    source.write_text(
        "\n".join(
            [
                "import logging",
                "logger = logging.getLogger(__name__)",
                "def process():",
                "    logger.debug('Transaction processing completed.')",
            ]
        ),
        encoding="utf-8",
    )

    assert evaluate_structured_log_guard((source,)) == []
