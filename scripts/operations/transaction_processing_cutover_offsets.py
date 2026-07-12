"""Safely hand Kafka offsets from legacy calculators to the combined worker."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from confluent_kafka import (
    Consumer,
    ConsumerGroupTopicPartitions,
    KafkaError,
    KafkaException,
    TopicPartition,
)
from confluent_kafka.admin import AdminClient
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
    KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
)

INVALID_OFFSET = -1001


class OffsetCutoverError(RuntimeError):
    """Raised when group state cannot support a lossless atomic handoff."""


@dataclass(frozen=True)
class PartitionOffset:
    topic: str
    partition: int
    committed_offset: int
    high_watermark: int

    @property
    def lag(self) -> int:
        return max(self.high_watermark - self.committed_offset, 0)


@dataclass(frozen=True)
class ConsumerGroupSnapshot:
    group_id: str
    active_member_count: int
    partitions: tuple[PartitionOffset, ...]


@dataclass(frozen=True)
class OffsetCutoverPlan:
    source_group: str
    target_group: str
    aligned_source_groups: tuple[str, ...]
    offsets: tuple[tuple[str, int, int], ...]
    requires_write: bool


@dataclass(frozen=True)
class CutoverSpec:
    name: str
    topic: str
    source_group: str
    target_group: str
    aligned_source_groups: tuple[str, ...] = ()
    allow_empty_uncommitted: bool = False


class OffsetStore(Protocol):
    def snapshot(self, *, group_id: str, topic: str) -> ConsumerGroupSnapshot: ...

    def write(self, plan: OffsetCutoverPlan) -> None: ...

    def close(self) -> None: ...


def build_offset_cutover_plan(
    *,
    source: ConsumerGroupSnapshot,
    target: ConsumerGroupSnapshot,
    aligned_sources: tuple[ConsumerGroupSnapshot, ...] = (),
    allow_empty_uncommitted: bool = False,
) -> OffsetCutoverPlan:
    if source.group_id == target.group_id:
        raise OffsetCutoverError("source and target groups must differ")
    if source.active_member_count:
        raise OffsetCutoverError(f"source group is active: {source.group_id}")
    if target.active_member_count:
        raise OffsetCutoverError(f"target group is active: {target.group_id}")
    if not source.partitions:
        raise OffsetCutoverError(f"source group has no topic partitions: {source.group_id}")

    source_offsets = _validated_drained_offsets(
        source,
        allow_empty_uncommitted=allow_empty_uncommitted,
    )
    for aligned in aligned_sources:
        if aligned.active_member_count:
            raise OffsetCutoverError(f"aligned source group is active: {aligned.group_id}")
        aligned_offsets = _validated_drained_offsets(aligned)
        if aligned_offsets != source_offsets:
            raise OffsetCutoverError(
                f"aligned source offsets differ: {source.group_id} != {aligned.group_id}"
            )

    target_offsets = {
        (item.topic, item.partition): item.committed_offset for item in target.partitions
    }
    offsets = tuple(
        (topic, partition, committed_offset)
        for (topic, partition), committed_offset in sorted(source_offsets.items())
    )
    requires_write = any(
        target_offsets.get((topic, partition), INVALID_OFFSET) != committed_offset
        for topic, partition, committed_offset in offsets
    )
    return OffsetCutoverPlan(
        source_group=source.group_id,
        target_group=target.group_id,
        aligned_source_groups=tuple(item.group_id for item in aligned_sources),
        offsets=offsets,
        requires_write=requires_write,
    )


def _validated_drained_offsets(
    snapshot: ConsumerGroupSnapshot,
    *,
    allow_empty_uncommitted: bool = False,
) -> dict[tuple[str, int], int]:
    offsets: dict[tuple[str, int], int] = {}
    for item in snapshot.partitions:
        committed_offset = item.committed_offset
        if committed_offset < 0 and allow_empty_uncommitted and item.high_watermark == 0:
            committed_offset = 0
        if committed_offset < 0:
            raise OffsetCutoverError(
                f"source group has no committed offset: {snapshot.group_id} "
                f"{item.topic}[{item.partition}]"
            )
        if committed_offset > item.high_watermark:
            raise OffsetCutoverError(
                f"source offset exceeds high watermark: {snapshot.group_id} "
                f"{item.topic}[{item.partition}]"
            )
        lag = max(item.high_watermark - committed_offset, 0)
        if lag:
            raise OffsetCutoverError(
                f"source group has committed lag: {snapshot.group_id} "
                f"{item.topic}[{item.partition}] lag={lag}"
            )
        key = (item.topic, item.partition)
        if key in offsets:
            raise OffsetCutoverError(f"duplicate source partition: {key}")
        offsets[key] = committed_offset
    return offsets


class KafkaOffsetStore:
    def __init__(self, *, bootstrap_servers: str, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds
        self._admin = AdminClient({"bootstrap.servers": bootstrap_servers})
        self._metadata_consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": "portfolio_transaction_cutover_inspector",
                "enable.auto.commit": False,
            }
        )

    def snapshot(self, *, group_id: str, topic: str) -> ConsumerGroupSnapshot:
        partitions = self._topic_partitions(topic)
        active_member_count = self._active_member_count(group_id)
        committed = self._committed_offsets(group_id, topic, partitions)
        rows = []
        for partition in partitions:
            _, high = self._metadata_consumer.get_watermark_offsets(
                TopicPartition(topic, partition),
                timeout=self._timeout_seconds,
                cached=False,
            )
            rows.append(
                PartitionOffset(
                    topic=topic,
                    partition=partition,
                    committed_offset=committed.get(partition, INVALID_OFFSET),
                    high_watermark=high,
                )
            )
        return ConsumerGroupSnapshot(
            group_id=group_id,
            active_member_count=active_member_count,
            partitions=tuple(rows),
        )

    def write(self, plan: OffsetCutoverPlan) -> None:
        request = ConsumerGroupTopicPartitions(
            plan.target_group,
            [TopicPartition(topic, partition, offset) for topic, partition, offset in plan.offsets],
        )
        future = self._admin.alter_consumer_group_offsets([request])[plan.target_group]
        future.result(timeout=self._timeout_seconds)

    def close(self) -> None:
        self._metadata_consumer.close()

    def _topic_partitions(self, topic: str) -> tuple[int, ...]:
        metadata = self._metadata_consumer.list_topics(topic, timeout=self._timeout_seconds)
        topic_metadata = metadata.topics.get(topic)
        if topic_metadata is None or topic_metadata.error is not None:
            raise OffsetCutoverError(f"Kafka topic is unavailable: {topic}")
        return tuple(sorted(topic_metadata.partitions))

    def _active_member_count(self, group_id: str) -> int:
        try:
            description = self._admin.describe_consumer_groups([group_id])[group_id].result(
                timeout=self._timeout_seconds
            )
        except KafkaException as exc:
            if _is_missing_group(exc):
                return 0
            raise
        return len(description.members)

    def _committed_offsets(
        self,
        group_id: str,
        topic: str,
        partitions: tuple[int, ...],
    ) -> dict[int, int]:
        request = ConsumerGroupTopicPartitions(
            group_id,
            [TopicPartition(topic, partition) for partition in partitions],
        )
        try:
            result = self._admin.list_consumer_group_offsets([request])[group_id].result(
                timeout=self._timeout_seconds
            )
        except KafkaException as exc:
            if _is_missing_group(exc):
                return {}
            raise
        return {
            item.partition: item.offset for item in result.topic_partitions if item.topic == topic
        }


def _is_missing_group(exc: KafkaException) -> bool:
    if not exc.args:
        return False
    error = exc.args[0]
    return isinstance(error, KafkaError) and error.code() == KafkaError._GROUP_ID_NOT_FOUND


def _default_specs(args: argparse.Namespace) -> tuple[CutoverSpec, ...]:
    return (
        CutoverSpec(
            name="live",
            topic=args.live_topic,
            source_group=args.live_source_group,
            target_group=args.live_target_group,
            aligned_source_groups=(args.live_aligned_group,),
        ),
        CutoverSpec(
            name="replay",
            topic=args.replay_topic,
            source_group=args.replay_source_group,
            target_group=args.replay_target_group,
            allow_empty_uncommitted=True,
        ),
    )


def execute_cutover(
    *,
    store: OffsetStore,
    specs: tuple[CutoverSpec, ...],
    apply: bool,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for spec in specs:
        source = store.snapshot(group_id=spec.source_group, topic=spec.topic)
        target = store.snapshot(group_id=spec.target_group, topic=spec.topic)
        aligned = tuple(
            store.snapshot(group_id=group_id, topic=spec.topic)
            for group_id in spec.aligned_source_groups
        )
        plan = build_offset_cutover_plan(
            source=source,
            target=target,
            aligned_sources=aligned,
            allow_empty_uncommitted=spec.allow_empty_uncommitted,
        )
        if apply and plan.requires_write:
            store.write(plan)
            verified = build_offset_cutover_plan(
                source=source,
                target=store.snapshot(group_id=spec.target_group, topic=spec.topic),
                aligned_sources=aligned,
                allow_empty_uncommitted=spec.allow_empty_uncommitted,
            )
            if verified.requires_write:
                raise OffsetCutoverError(f"target offset verification failed: {spec.name}")
        results.append(
            {
                "name": spec.name,
                "topic": spec.topic,
                "source": asdict(source),
                "target_before": asdict(target),
                "plan": asdict(plan),
                "applied": apply and plan.requires_write,
            }
        )
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and transfer calculator offsets to the combined transaction worker."
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", KAFKA_BOOTSTRAP_SERVERS),
    )
    parser.add_argument("--live-topic", default=KAFKA_TRANSACTIONS_PERSISTED_TOPIC)
    parser.add_argument("--live-source-group", default="cost_calculator_group")
    parser.add_argument("--live-aligned-group", default="cashflow_calculator_group")
    parser.add_argument(
        "--live-target-group",
        default="portfolio_transaction_processing_group",
    )
    parser.add_argument(
        "--replay-topic",
        default=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
    )
    parser.add_argument("--replay-source-group", default="cost_reprocessing_group")
    parser.add_argument(
        "--replay-target-group",
        default="portfolio_transaction_replay_request_group",
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/transaction-processing-offset-cutover.json"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write and verify target offsets. Omit for the default dry-run audit.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    store = KafkaOffsetStore(
        bootstrap_servers=args.bootstrap_servers,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        results = execute_cutover(store=store, specs=_default_specs(args), apply=args.apply)
        report: dict[str, object] = {
            "schema": "lotus-core.transaction-processing-offset-cutover.v1",
            "generated_at": generated_at,
            "mode": "apply" if args.apply else "dry-run",
            "status": "applied" if args.apply else "ready",
            "results": results,
        }
        exit_code = 0
    except (KafkaException, OffsetCutoverError) as exc:
        report = {
            "schema": "lotus-core.transaction-processing-offset-cutover.v1",
            "generated_at": generated_at,
            "mode": "apply" if args.apply else "dry-run",
            "status": "blocked",
            "error": str(exc),
        }
        exit_code = 1
    finally:
        store.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
