import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from confluent_kafka import KafkaException, Producer

from .config import KAFKA_BOOTSTRAP_SERVERS

logger = logging.getLogger(__name__)


class KafkaProducer:
    """
    Thin wrapper around confluent_kafka.Producer with production-safe defaults:
    - Idempotence enabled for exactly-once produce within a session
    - Strong durability (acks=all) and bounded in-flight requests
    - Moderate batching and compression for throughput
    Notes:
      * We do NOT enable transactions here; outbox DB state + idempotent produces is
        already a strong reliability baseline. Transactions can be added later if desired.
    """

    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
        self.producer = None
        self.bootstrap_servers = bootstrap_servers
        self._initialize_producer()

    def _initialize_producer(self):
        try:
            conf = {
                # Broker connectivity
                "bootstrap.servers": self.bootstrap_servers,
                "client.id": "portfolio-analytics-producer",
                # Reliability
                "enable.idempotence": True,  # ensure de-dup on broker
                "acks": "all",
                "retries": 5,
                "max.in.flight.requests.per.connection": 5,  # safe with idempotence
                # Throughput (tune as needed per env)
                "linger.ms": 5,
                "batch.num.messages": 1000,
                "compression.type": "zstd",
                # Timeouts & keepalive
                "delivery.timeout.ms": 120000,  # cap end-to-end delivery
                "request.timeout.ms": 30000,
                "socket.keepalive.enable": True,
            }

            self.producer = Producer(conf)
            logger.info(f"Kafka producer initialized for brokers: {self.bootstrap_servers}")
        except KafkaException as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            self.producer = None
            raise

    def publish_message(
        self,
        topic: str,
        key: str,
        value: Dict[str, Any],
        headers: Optional[List[Tuple[str, bytes]]] = None,
        *,
        outbox_id: Optional[str] = None,
        on_delivery: Optional[Callable[[str, bool, Optional[str]], None]] = None,
    ):
        """
        Publish a message and optionally invoke an external on_delivery callback
        with the original outbox_id.
        on_delivery(outbox_id, success, error_message)
        """
        if not self.producer:
            logger.error(
                f"Kafka producer not initialized. Cannot publish message to topic {topic}."
            )
            raise RuntimeError("Kafka producer is not initialized.")

        try:
            json_value = json.dumps(value, default=str)
            publish_headers = _publish_headers(headers, outbox_id)

            self.producer.produce(
                topic,
                key=_encoded_kafka_key(key),
                value=json_value.encode("utf-8"),
                headers=publish_headers,
                callback=_delivery_report_callback(outbox_id, on_delivery),
            )
            self.producer.poll(0)
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during message production: {e}", exc_info=True
            )
            raise

    def flush(self, timeout: int = 10):
        if self.producer:
            return self.producer.flush(timeout)
        return 0

    def close(self, timeout: int = 10) -> None:
        if self.producer:
            try:
                undelivered_count = self.producer.flush(timeout)
                if undelivered_count:
                    logger.error(
                        "Kafka producer close left undelivered messages.",
                        extra={"undelivered_count": undelivered_count, "timeout": timeout},
                    )
            except Exception:
                logger.error("Kafka producer close flush failed.", exc_info=True)
            finally:
                self.producer = None


_kafka_producer_instance = None


def get_kafka_producer() -> KafkaProducer:
    global _kafka_producer_instance
    if _kafka_producer_instance is None:
        _kafka_producer_instance = KafkaProducer()
    return _kafka_producer_instance


def reset_kafka_producer(*, timeout: int = 10) -> None:
    global _kafka_producer_instance
    if _kafka_producer_instance is not None:
        try:
            _kafka_producer_instance.close(timeout=timeout)
        finally:
            _kafka_producer_instance = None


def _publish_headers(
    headers: Optional[List[Tuple[str, bytes]]],
    outbox_id: Optional[str],
) -> List[Tuple[str, bytes]]:
    publish_headers = headers[:] if headers else []
    if outbox_id:
        publish_headers.append(("outbox_id", outbox_id.encode("utf-8")))
    return publish_headers


def _encoded_kafka_key(key: object):
    return key.encode("utf-8") if isinstance(key, str) else key


def _delivery_report_callback(
    outbox_id: Optional[str],
    on_delivery: Optional[Callable[[str, bool, Optional[str]], None]],
):
    def delivery_report(err, msg):
        resolved_outbox_id = outbox_id or _outbox_id_from_message_headers(msg)
        if err is not None:
            _handle_delivery_failure(err, msg, resolved_outbox_id, on_delivery)
            return
        _handle_delivery_success(msg, resolved_outbox_id, on_delivery)

    return delivery_report


def _outbox_id_from_message_headers(msg) -> Optional[str]:
    try:
        raw = dict(msg.headers() or []).get("outbox_id")
    except Exception:
        return None
    return _decoded_outbox_id(raw)


def _decoded_outbox_id(raw: object) -> Optional[str]:
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode("utf-8")
    if isinstance(raw, str):
        return raw
    return None


def _handle_delivery_failure(
    err,
    msg,
    outbox_id: Optional[str],
    on_delivery: Optional[Callable[[str, bool, Optional[str]], None]],
) -> None:
    logger.error(f"Message delivery failed for topic {msg.topic()} key {msg.key()}: {err}")
    _notify_delivery_callback(
        on_delivery,
        outbox_id,
        success=False,
        error_message=str(err),
        failure_log_message="on_delivery callback raised an exception (failure path).",
    )


def _handle_delivery_success(
    msg,
    outbox_id: Optional[str],
    on_delivery: Optional[Callable[[str, bool, Optional[str]], None]],
) -> None:
    logger.info(
        f"Message delivered with key '{_message_key_repr(msg)}'",
        extra=_delivery_log_extra(msg),
    )
    _notify_delivery_callback(
        on_delivery,
        outbox_id,
        success=True,
        error_message=None,
        failure_log_message="on_delivery callback raised an exception (success path).",
    )


def _delivery_log_extra(msg) -> Dict[str, Any]:
    return {
        "topic": msg.topic(),
        "partition": msg.partition(),
        "offset": msg.offset(),
    }


def _message_key_repr(msg) -> str:
    try:
        return msg.key().decode("utf-8") if msg.key() else ""
    except Exception:
        return "<binary>"


def _notify_delivery_callback(
    on_delivery: Optional[Callable[[Optional[str], bool, Optional[str]], None]],
    outbox_id: Optional[str],
    *,
    success: bool,
    error_message: Optional[str],
    failure_log_message: str,
) -> None:
    if not on_delivery:
        return
    try:
        on_delivery(outbox_id, success, error_message)
    except Exception:
        logger.exception(failure_log_message)
