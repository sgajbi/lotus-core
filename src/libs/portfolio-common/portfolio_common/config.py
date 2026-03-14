# libs/portfolio-common/portfolio_common/config.py
import json
import logging
import os

from dotenv import load_dotenv

# Load environment variables from a .env file for local development.
load_dotenv()
logger = logging.getLogger(__name__)


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
KAFKA_RAW_PORTFOLIOS_TOPIC = os.getenv("KAFKA_RAW_PORTFOLIOS_TOPIC", "raw_portfolios")
KAFKA_RAW_TRANSACTIONS_TOPIC = os.getenv("KAFKA_RAW_TRANSACTIONS_TOPIC", "raw_transactions")
KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC = os.getenv(
    "KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC", "raw_transactions_completed"
)
KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC = os.getenv(
    "KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC", "processed_transactions_completed"
)
KAFKA_TRANSACTION_PROCESSING_COMPLETED_TOPIC = os.getenv(
    "KAFKA_TRANSACTION_PROCESSING_COMPLETED_TOPIC", "transaction_processing_completed"
)
KAFKA_INSTRUMENTS_TOPIC = os.getenv("KAFKA_INSTRUMENTS_TOPIC", "instruments")
KAFKA_MARKET_PRICES_TOPIC = os.getenv("KAFKA_MARKET_PRICES_TOPIC", "market_prices")
KAFKA_MARKET_PRICE_PERSISTED_TOPIC = os.getenv(
    "KAFKA_MARKET_PRICE_PERSISTED_TOPIC", "market_price_persisted"
)
KAFKA_FX_RATES_TOPIC = os.getenv("KAFKA_FX_RATES_TOPIC", "fx_rates")
KAFKA_RAW_BUSINESS_DATES_TOPIC = os.getenv(
    "KAFKA_RAW_BUSINESS_DATES_TOPIC", "raw_business_dates"
)  # New Topic
KAFKA_PERSISTENCE_DLQ_TOPIC = os.getenv("KAFKA_PERSISTENCE_DLQ_TOPIC", "persistence_service.dlq")
KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC = os.getenv(
    "KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC", "daily_position_snapshot_persisted"
)
KAFKA_POSITION_VALUED_TOPIC = os.getenv("KAFKA_POSITION_VALUED_TOPIC", "position_valued")
KAFKA_CASHFLOW_CALCULATED_TOPIC = os.getenv(
    "KAFKA_CASHFLOW_CALCULATED_TOPIC", "cashflow_calculated"
)
KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC = os.getenv(
    "KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC", "position_timeseries_generated"
)
KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC", "portfolio_timeseries_generated"
)
KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC", "portfolio_aggregation_required"
)
KAFKA_VALUATION_REQUIRED_TOPIC = os.getenv("KAFKA_VALUATION_REQUIRED_TOPIC", "valuation_required")
KAFKA_PORTFOLIO_DAY_READY_FOR_VALUATION_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_DAY_READY_FOR_VALUATION_TOPIC", "portfolio_day_ready_for_valuation"
)
KAFKA_VALUATION_DAY_COMPLETED_TOPIC = os.getenv(
    "KAFKA_VALUATION_DAY_COMPLETED_TOPIC", "valuation_day_completed"
)
KAFKA_POSITION_TIMESERIES_DAY_COMPLETED_TOPIC = os.getenv(
    "KAFKA_POSITION_TIMESERIES_DAY_COMPLETED_TOPIC", "position_timeseries_day_completed"
)
KAFKA_PORTFOLIO_AGGREGATION_DAY_COMPLETED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_AGGREGATION_DAY_COMPLETED_TOPIC", "portfolio_aggregation_day_completed"
)
KAFKA_FINANCIAL_RECONCILIATION_REQUESTED_TOPIC = os.getenv(
    "KAFKA_FINANCIAL_RECONCILIATION_REQUESTED_TOPIC", "financial_reconciliation_requested"
)
KAFKA_FINANCIAL_RECONCILIATION_COMPLETED_TOPIC = os.getenv(
    "KAFKA_FINANCIAL_RECONCILIATION_COMPLETED_TOPIC", "financial_reconciliation_completed"
)
KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC = os.getenv(
    "KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC", "portfolio_day_controls_evaluated"
)

# Business-date calendar and guardrail policy
DEFAULT_BUSINESS_CALENDAR_CODE = os.getenv("DEFAULT_BUSINESS_CALENDAR_CODE", "GLOBAL")
BUSINESS_DATE_MAX_FUTURE_DAYS = _env_int("BUSINESS_DATE_MAX_FUTURE_DAYS", 0, minimum=0)
BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE = os.getenv(
    "BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}

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
