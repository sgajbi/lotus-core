import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from confluent_kafka import KafkaException, Producer

from .config import KAFKA_BOOTSTRAP_SERVERS
from .kafka_producer_policy import (
    DEFAULT_PRODUCER_SERVICE,
    KafkaProducerPolicy,
    load_kafka_producer_policy,
)
from .logging_utils import operation_log_extra
from .monitoring import observe_kafka_producer_event

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

    def __init__(
        self,
        bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
        *,
        service_name: str = DEFAULT_PRODUCER_SERVICE,
        producer_policy: KafkaProducerPolicy | None = None,
    ):
        self.producer = None
        self.bootstrap_servers = bootstrap_servers
        self.service_name = service_name
        self.producer_policy = producer_policy or load_kafka_producer_policy(
            service_name=service_name
        )
        self._initialize_producer()

    def _initialize_producer(self):
        try:
            conf = {
                # Broker connectivity
                "bootstrap.servers": self.bootstrap_servers,
                # Reliability
                "enable.idempotence": True,  # ensure de-dup on broker
                "acks": "all",
                "max.in.flight.requests.per.connection": 5,  # safe with idempotence
                "socket.keepalive.enable": True,
            }
            conf.update(self.producer_policy.as_confluent_config())

            self.producer = Producer(conf)
            broker_count = len([server for server in self.bootstrap_servers.split(",") if server])
            logger.info(
                "Kafka producer initialized.",
                extra=operation_log_extra(
                    event_name="kafka.producer.initialized",
                    operation="kafka.produce",
                    status="succeeded",
                    reason_code="producer_initialized",
                    broker_count=broker_count,
                    service=self.service_name,
                    client_id=self.producer_policy.client_id,
                ),
            )
        except KafkaException as e:
            logger.error(
                "Kafka producer initialization failed.",
                exc_info=True,
                extra=operation_log_extra(
                    event_name="kafka.producer.initialization_failed",
                    operation="kafka.produce",
                    status="failed",
                    reason_code="producer_initialization_error",
                    error_type=type(e).__name__,
                    service=self.service_name,
                ),
            )
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
                "Kafka producer is not initialized.",
                extra=operation_log_extra(
                    event_name="kafka.producer.publish_rejected",
                    operation="kafka.produce",
                    status="failed",
                    reason_code="producer_not_initialized",
                    topic=topic,
                ),
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
            observe_kafka_producer_event(
                service=self.service_name,
                topic=topic,
                outcome="accepted",
                reason="produce_queued",
            )
        except BufferError:
            observe_kafka_producer_event(
                service=self.service_name,
                topic=topic,
                outcome="back_pressure",
                reason="queue_full",
            )
            logger.warning(
                "Kafka producer local queue is saturated.",
                extra=operation_log_extra(
                    event_name="kafka.producer.back_pressure",
                    operation="kafka.produce",
                    status="failed",
                    reason_code="queue_full",
                    topic=topic,
                    service=self.service_name,
                ),
            )
            raise
        except Exception as e:
            observe_kafka_producer_event(
                service=self.service_name,
                topic=topic,
                outcome="failed",
                reason="producer_publish_error",
            )
            logger.error(
                "Kafka message production failed.",
                exc_info=True,
                extra=operation_log_extra(
                    event_name="kafka.producer.publish_failed",
                    operation="kafka.produce",
                    status="failed",
                    reason_code="producer_publish_error",
                    topic=topic,
                    error_type=type(e).__name__,
                ),
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
                        extra=operation_log_extra(
                            event_name="kafka.producer.close_incomplete",
                            operation="kafka.produce",
                            status="failed",
                            reason_code="undelivered_messages",
                            undelivered_count=undelivered_count,
                            timeout_seconds=timeout,
                        ),
                    )
            except Exception:
                logger.error(
                    "Kafka producer close flush failed.",
                    exc_info=True,
                    extra=operation_log_extra(
                        event_name="kafka.producer.close_failed",
                        operation="kafka.produce",
                        status="failed",
                        reason_code="producer_flush_error",
                        timeout_seconds=timeout,
                    ),
                )
            finally:
                self.producer = None


_kafka_producer_instances: dict[tuple[str, str], KafkaProducer] = {}


def get_kafka_producer(
    *,
    bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
    service_name: str = DEFAULT_PRODUCER_SERVICE,
) -> KafkaProducer:
    key = (bootstrap_servers, service_name)
    if key not in _kafka_producer_instances:
        _kafka_producer_instances[key] = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            service_name=service_name,
        )
    return _kafka_producer_instances[key]


def reset_kafka_producer(*, timeout: int = 10) -> None:
    global _kafka_producer_instances
    instances = list(_kafka_producer_instances.values())
    _kafka_producer_instances = {}
    for instance in instances:
        try:
            instance.close(timeout=timeout)
        except Exception:
            logger.exception("Kafka producer reset close failed.")


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
    logger.error(
        "Kafka message delivery failed.",
        extra=operation_log_extra(
            event_name="kafka.producer.delivery_failed",
            operation="kafka.produce",
            status="failed",
            reason_code="delivery_error",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            error_type=type(err).__name__,
        ),
    )
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
        "Kafka message delivered.",
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
    return operation_log_extra(
        event_name="kafka.producer.delivery_succeeded",
        operation="kafka.produce",
        status="succeeded",
        reason_code="delivery_acknowledged",
        topic=msg.topic(),
        partition=msg.partition(),
        offset=msg.offset(),
    )


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
