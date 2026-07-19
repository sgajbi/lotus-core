"""Verify the event runtime inventory remains complete and aligned with executable policy."""

import json
import zlib
from collections import Counter
from pathlib import Path

from portfolio_common.config import KAFKA_TOPIC_PARTITION_COUNTS
from portfolio_common.kafka_consumer_execution import GOVERNED_GROUP_MAX_IN_FLIGHT

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "contracts/eventing/kafka-topic-runtime-contract.v1.json"
CANONICAL_MARKET_PRICE_KEYS = (
    "CASH_EUR_BOOK_OPERATING",
    "CASH_USD_BOOK_OPERATING",
    "FO_BOND_UST_2030",
    "FO_EQ_AAPL_US",
    "FO_EQ_MSFT_US",
    "FO_EQ_SAP_DE",
    "FO_ETF_MSCI_WORLD",
    "FO_FUND_BLK_ALLOC",
    "FO_FUND_PIMCO_INC",
    "FO_PRIV_PRIVATE_CREDIT_A",
)


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_contract_inventories_every_active_topic_once() -> None:
    topics = _contract()["topics"]
    topic_names = [topic["topic"] for topic in topics]

    assert len(topic_names) == len(set(topic_names))
    assert set(topic_names) == set(KAFKA_TOPIC_PARTITION_COUNTS)


def test_contract_partition_and_consumer_capacity_match_runtime_policy() -> None:
    for topic in _contract()["topics"]:
        assert topic["partitions"] == KAFKA_TOPIC_PARTITION_COUNTS[topic["topic"]]
        consumer_groups = topic["consumer_groups"]
        if not consumer_groups:
            assert topic["consumer_max_in_flight"] == 0
            continue
        assert len(consumer_groups) == 1
        assert topic["consumer_max_in_flight"] == GOVERNED_GROUP_MAX_IN_FLIGHT[consumer_groups[0]]
        assert topic["consumer_max_in_flight"] <= topic["partitions"]


def test_contract_records_ordering_replay_and_tenant_truth() -> None:
    contract = _contract()

    assert contract["tenant_identity_status"] == "not_source_owned_in_current_event_family"
    assert contract["keyed_partitioner"] == "consistent_random_crc32"
    for topic in contract["topics"]:
        assert topic["current_key"]
        assert topic["ordering_scope"]
        assert topic["state_owner"]
        assert topic["duplicate_policy"]
        assert topic["replay_contract"]


def test_market_price_capacity_bounds_canonical_key_skew() -> None:
    topics = {topic["topic"]: topic for topic in _contract()["topics"]}
    raw = topics["market_prices.raw.received"]
    persisted = topics["market_prices.persisted"]

    assert raw["partitions"] == persisted["partitions"] == 12
    distribution = Counter(
        zlib.crc32(key.encode("utf-8")) % raw["partitions"] for key in CANONICAL_MARKET_PRICE_KEYS
    )

    assert len(distribution) == 7
    assert max(distribution.values()) == 3
