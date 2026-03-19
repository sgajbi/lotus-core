# libs/portfolio-common/portfolio_common/config.py
import json
import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load environment variables from a .env file for local development.
load_dotenv()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KafkaTopicDefinition:
    canonical_name: str
    runtime_name: str
    lifecycle_status: str
    semantic_type: str
    scope: str


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    try:
        safe_default = int(default)
    except Exception:
        safe_default = 0

    raw = os.getenv(name)
    if raw is None:
        value = safe_default
    else:
        try:
            value = int(raw)
        except Exception:
            logger.warning(
                "Invalid integer env setting; falling back to default.",
                extra={"setting": name, "raw_value": raw, "default": safe_default},
            )
            value = safe_default

    if minimum is not None and value < minimum:
        logger.warning(
            "Out-of-range integer env setting; falling back to default.",
            extra={
                "setting": name,
                "raw_value": raw,
                "default": safe_default,
                "minimum": minimum,
            },
        )
        return safe_default if safe_default >= minimum else minimum

    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logger.warning(
        "Invalid boolean env setting; falling back to default.",
        extra={"setting": name, "raw_value": raw, "default": default},
    )
    return default


# Database Configurations
POSTGRES_USER = os.getenv("POSTGRES_USER", "user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "portfolio_db")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

MONGO_INITDB_ROOT_USERNAME = os.getenv("MONGO_INITDB_ROOT_USERNAME", "admin")
MONGO_INITDB_ROOT_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "password")
MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
MONGO_PORT = os.getenv("MONGO_PORT", "2717")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "portfolio_state")
MONGO_URL = (
    f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}"
)

# Kafka Configurations
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS_HOST") or os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS", "kafka:9093"
)
KAFKA_PORTFOLIOS_RAW_RECEIVED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIOS_RAW_RECEIVED_TOPIC", "portfolios.raw.received"
)
KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC = os.getenv(
    "KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC", "transactions.raw.received"
)
KAFKA_TRANSACTIONS_PERSISTED_TOPIC = os.getenv(
    "KAFKA_TRANSACTIONS_PERSISTED_TOPIC", "transactions.persisted"
)
KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC = os.getenv(
    "KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC", "transactions.cost.processed"
)
KAFKA_TRANSACTION_PROCESSING_READY_TOPIC = os.getenv(
    "KAFKA_TRANSACTION_PROCESSING_READY_TOPIC", "transaction_processing.ready"
)
KAFKA_INSTRUMENTS_RECEIVED_TOPIC = os.getenv(
    "KAFKA_INSTRUMENTS_RECEIVED_TOPIC", "instruments.received"
)
KAFKA_MARKET_PRICES_RAW_RECEIVED_TOPIC = os.getenv(
    "KAFKA_MARKET_PRICES_RAW_RECEIVED_TOPIC", "market_prices.raw.received"
)
KAFKA_MARKET_PRICES_PERSISTED_TOPIC = os.getenv(
    "KAFKA_MARKET_PRICES_PERSISTED_TOPIC", "market_prices.persisted"
)
KAFKA_FX_RATES_RAW_RECEIVED_TOPIC = os.getenv(
    "KAFKA_FX_RATES_RAW_RECEIVED_TOPIC", "fx_rates.raw.received"
)
KAFKA_BUSINESS_DATES_RAW_RECEIVED_TOPIC = os.getenv(
    "KAFKA_BUSINESS_DATES_RAW_RECEIVED_TOPIC", "business_dates.raw.received"
)
KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC = os.getenv(
    "KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC", "dlq.persistence_service"
)
KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC = os.getenv(
    "KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC", "valuation.snapshot.persisted"
)
KAFKA_CASHFLOWS_CALCULATED_TOPIC = os.getenv(
    "KAFKA_CASHFLOWS_CALCULATED_TOPIC", "cashflows.calculated"
)
KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC",
    "portfolio_day.aggregation.job.requested",
)
KAFKA_VALUATION_JOB_REQUESTED_TOPIC = os.getenv(
    "KAFKA_VALUATION_JOB_REQUESTED_TOPIC", "valuation.job.requested"
)
KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC",
    "portfolio_security_day.valuation.ready",
)
KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_COMPLETED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_COMPLETED_TOPIC",
    "portfolio_security_day.valuation.completed",
)
KAFKA_PORTFOLIO_SECURITY_DAY_POSITION_TIMESERIES_COMPLETED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_SECURITY_DAY_POSITION_TIMESERIES_COMPLETED_TOPIC",
    "portfolio_security_day.position_timeseries.completed",
)
KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC",
    "portfolio_day.aggregation.completed",
)
KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC",
    "portfolio_day.reconciliation.requested",
)
KAFKA_PORTFOLIO_DAY_RECONCILIATION_COMPLETED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_DAY_RECONCILIATION_COMPLETED_TOPIC",
    "portfolio_day.reconciliation.completed",
)
KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC", "portfolio_day.controls.evaluated"
)
KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC = os.getenv(
    "KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC", "transactions.reprocessing.requested"
)

KAFKA_TOPIC_DEFINITIONS = (
    KafkaTopicDefinition(
        canonical_name="portfolios.raw.received",
        runtime_name=KAFKA_PORTFOLIOS_RAW_RECEIVED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="portfolio",
    ),
    KafkaTopicDefinition(
        canonical_name="transactions.raw.received",
        runtime_name=KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="transaction",
    ),
    KafkaTopicDefinition(
        canonical_name="instruments.received",
        runtime_name=KAFKA_INSTRUMENTS_RECEIVED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="instrument",
    ),
    KafkaTopicDefinition(
        canonical_name="market_prices.raw.received",
        runtime_name=KAFKA_MARKET_PRICES_RAW_RECEIVED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="market_price",
    ),
    KafkaTopicDefinition(
        canonical_name="fx_rates.raw.received",
        runtime_name=KAFKA_FX_RATES_RAW_RECEIVED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="fx_rate",
    ),
    KafkaTopicDefinition(
        canonical_name="business_dates.raw.received",
        runtime_name=KAFKA_BUSINESS_DATES_RAW_RECEIVED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="business_date",
    ),
    KafkaTopicDefinition(
        canonical_name="transactions.persisted",
        runtime_name=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="transaction",
    ),
    KafkaTopicDefinition(
        canonical_name="market_prices.persisted",
        runtime_name=KAFKA_MARKET_PRICES_PERSISTED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="market_price",
    ),
    KafkaTopicDefinition(
        canonical_name="transactions.cost.processed",
        runtime_name=KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="transaction",
    ),
    KafkaTopicDefinition(
        canonical_name="transaction_processing.ready",
        runtime_name=KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
        lifecycle_status="active",
        semantic_type="readiness",
        scope="transaction",
    ),
    KafkaTopicDefinition(
        canonical_name="cashflows.calculated",
        runtime_name=KAFKA_CASHFLOWS_CALCULATED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="transaction",
    ),
    KafkaTopicDefinition(
        canonical_name="valuation.snapshot.persisted",
        runtime_name=KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="portfolio_security_day",
    ),
    KafkaTopicDefinition(
        canonical_name="valuation.job.requested",
        runtime_name=KAFKA_VALUATION_JOB_REQUESTED_TOPIC,
        lifecycle_status="active",
        semantic_type="command",
        scope="portfolio_security_day",
    ),
    KafkaTopicDefinition(
        canonical_name="portfolio_security_day.valuation.ready",
        runtime_name=KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
        lifecycle_status="active",
        semantic_type="readiness",
        scope="portfolio_security_day",
    ),
    KafkaTopicDefinition(
        canonical_name="portfolio_security_day.valuation.completed",
        runtime_name=KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_COMPLETED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="portfolio_security_day",
    ),
    KafkaTopicDefinition(
        canonical_name="portfolio_security_day.position_timeseries.completed",
        runtime_name=KAFKA_PORTFOLIO_SECURITY_DAY_POSITION_TIMESERIES_COMPLETED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="portfolio_security_day",
    ),
    KafkaTopicDefinition(
        canonical_name="portfolio_day.aggregation.job.requested",
        runtime_name=KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC,
        lifecycle_status="active",
        semantic_type="command",
        scope="portfolio_day",
    ),
    KafkaTopicDefinition(
        canonical_name="portfolio_day.aggregation.completed",
        runtime_name=KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="portfolio_day",
    ),
    KafkaTopicDefinition(
        canonical_name="portfolio_day.reconciliation.requested",
        runtime_name=KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
        lifecycle_status="active",
        semantic_type="command",
        scope="portfolio_day",
    ),
    KafkaTopicDefinition(
        canonical_name="portfolio_day.reconciliation.completed",
        runtime_name=KAFKA_PORTFOLIO_DAY_RECONCILIATION_COMPLETED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="portfolio_day",
    ),
    KafkaTopicDefinition(
        canonical_name="portfolio_day.controls.evaluated",
        runtime_name=KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC,
        lifecycle_status="active",
        semantic_type="fact",
        scope="portfolio_day",
    ),
    KafkaTopicDefinition(
        canonical_name="transactions.reprocessing.requested",
        runtime_name=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
        lifecycle_status="active",
        semantic_type="command",
        scope="transaction",
    ),
    KafkaTopicDefinition(
        canonical_name="dlq.persistence_service",
        runtime_name=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
        lifecycle_status="active",
        semantic_type="dlq",
        scope="service",
    ),
    KafkaTopicDefinition(
        canonical_name="positions.valued",
        runtime_name="positions.valued",
        lifecycle_status="inactive",
        semantic_type="fact",
        scope="portfolio_security_day",
    ),
    KafkaTopicDefinition(
        canonical_name="timeseries.position.generated",
        runtime_name="timeseries.position.generated",
        lifecycle_status="inactive",
        semantic_type="fact",
        scope="portfolio_security_day",
    ),
    KafkaTopicDefinition(
        canonical_name="timeseries.portfolio.generated",
        runtime_name="timeseries.portfolio.generated",
        lifecycle_status="inactive",
        semantic_type="fact",
        scope="portfolio_day",
    ),
)

KAFKA_TOPIC_RUNTIME_NAMES = tuple(
    dict.fromkeys(
        topic.runtime_name
        for topic in KAFKA_TOPIC_DEFINITIONS
        if topic.lifecycle_status == "active"
    )
)

# Business-date calendar and guardrail policy
DEFAULT_BUSINESS_CALENDAR_CODE = os.getenv("DEFAULT_BUSINESS_CALENDAR_CODE", "GLOBAL")
BUSINESS_DATE_MAX_FUTURE_DAYS = _env_int("BUSINESS_DATE_MAX_FUTURE_DAYS", 0, minimum=0)
BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE = _env_bool(
    "BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE", False
)

# Cashflow calculator runtime cache policy
CASHFLOW_RULE_CACHE_TTL_SECONDS = _env_int("CASHFLOW_RULE_CACHE_TTL_SECONDS", 300, minimum=1)


_CONSUMER_ALLOWED_TYPES: dict[str, type] = {
    "auto.offset.reset": str,
    "enable.auto.commit": bool,
    "session.timeout.ms": int,
    "heartbeat.interval.ms": int,
    "max.poll.interval.ms": int,
    "fetch.min.bytes": int,
    "fetch.max.bytes": int,
    "max.partition.fetch.bytes": int,
    "queued.min.messages": int,
    "queued.max.messages.kbytes": int,
}
_AUTO_OFFSET_RESET_ALLOWED_VALUES = {"earliest", "latest", "error"}
_POSITIVE_INT_CONSUMER_KEYS = {
    "session.timeout.ms",
    "heartbeat.interval.ms",
    "max.poll.interval.ms",
    "fetch.min.bytes",
    "fetch.max.bytes",
    "max.partition.fetch.bytes",
    "queued.min.messages",
    "queued.max.messages.kbytes",
}


def _coerce_consumer_config_value(key: str, value: object) -> object:
    expected = _CONSUMER_ALLOWED_TYPES[key]
    if expected is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        raise ValueError(f"Expected bool for '{key}', got {value!r}")
    if expected is int:
        if isinstance(value, bool):
            raise ValueError(f"Expected int for '{key}', got {value!r}")
        if isinstance(value, int):
            coerced = value
        elif isinstance(value, str):
            coerced = int(value.strip())
        else:
            raise ValueError(f"Expected int for '{key}', got {value!r}")
        if key in _POSITIVE_INT_CONSUMER_KEYS and coerced <= 0:
            raise ValueError(f"Expected positive int for '{key}', got {value!r}")
        return coerced
    if expected is str:
        if isinstance(value, str):
            if key == "auto.offset.reset":
                normalized = value.strip().lower()
                if normalized not in _AUTO_OFFSET_RESET_ALLOWED_VALUES:
                    raise ValueError(
                        "Expected one of "
                        f"{sorted(_AUTO_OFFSET_RESET_ALLOWED_VALUES)} for '{key}', got {value!r}"
                    )
                return normalized
            return value
        raise ValueError(f"Expected str for '{key}', got {value!r}")
    return value


def _sanitize_consumer_override_map(raw: object, *, context: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must be a JSON object.")
    sanitized: dict[str, object] = {}
    for key, value in raw.items():
        if key not in _CONSUMER_ALLOWED_TYPES:
            logger.warning(
                "Ignoring unsupported Kafka consumer config key.",
                extra={"key": key, "context": context},
            )
            continue
        try:
            sanitized[key] = _coerce_consumer_config_value(key, value)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning(
                "Ignoring invalid Kafka consumer config value.",
                extra={"key": key, "value": value, "context": context, "error": str(exc)},
            )
    return sanitized


def _validate_consumer_override_relationships(
    overrides: dict[str, object], *, context: str
) -> dict[str, object]:
    validated = dict(overrides)
    session_timeout = validated.get("session.timeout.ms")
    heartbeat_interval = validated.get("heartbeat.interval.ms")
    if (
        isinstance(session_timeout, int)
        and isinstance(heartbeat_interval, int)
        and heartbeat_interval >= session_timeout
    ):
        logger.warning(
            "Ignoring invalid Kafka consumer heartbeat/session relationship.",
            extra={
                "context": context,
                "heartbeat.interval.ms": heartbeat_interval,
                "session.timeout.ms": session_timeout,
            },
        )
        validated.pop("heartbeat.interval.ms", None)
    return validated


def get_kafka_consumer_runtime_overrides(group_id: str) -> dict[str, object]:
    """
    Loads optional runtime Kafka consumer tuning from environment variables.
    - LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON: global defaults
    - LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON: map keyed by group_id
    """
    merged: dict[str, object] = {}

    defaults_raw = os.getenv("LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON", "").strip()
    if defaults_raw:
        try:
            defaults = json.loads(defaults_raw)
            merged.update(
                _validate_consumer_override_relationships(
                    _sanitize_consumer_override_map(
                        defaults, context="LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON"
                    ),
                    context="LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON",
                )
            )
        except Exception as exc:
            logger.warning("Invalid consumer defaults JSON; ignoring.", extra={"error": str(exc)})

    group_raw = os.getenv("LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON", "").strip()
    if group_raw:
        try:
            parsed = json.loads(group_raw)
            if isinstance(parsed, dict):
                group_cfg = parsed.get(group_id)
                if group_cfg is not None:
                    merged.update(
                        _validate_consumer_override_relationships(
                            _sanitize_consumer_override_map(
                                group_cfg,
                                context=(
                                    "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON"
                                    f"[{group_id}]"
                                ),
                            ),
                            context=(
                                "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON"
                                f"[{group_id}]"
                            ),
                        )
                    )
            else:
                logger.warning("Group overrides JSON must be an object; ignoring.")
        except Exception as exc:
            logger.warning(
                "Invalid consumer group overrides JSON; ignoring.", extra={"error": str(exc)}
            )

    return _validate_consumer_override_relationships(
        merged,
        context=f"merged Kafka consumer runtime overrides for group '{group_id}'",
    )
