from tools import kafka_setup


def test_portfolio_aggregation_job_topic_uses_specific_partition_override(monkeypatch):
    monkeypatch.setattr(kafka_setup, "NUM_PARTITIONS", 1)
    monkeypatch.setattr(kafka_setup, "PORTFOLIO_AGGREGATION_JOB_PARTITIONS", 4)

    assert (
        kafka_setup._partition_count_for_topic(
            kafka_setup.KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC
        )
        == 4
    )
    assert kafka_setup._partition_count_for_topic("transactions.persisted") == 1
