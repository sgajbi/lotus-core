from portfolio_common.database_models import (
    AnalyticsExportJob,
    PortfolioAggregationJob,
    PortfolioValuationJob,
    ReprocessingJob,
)


def test_reprocessing_job_declares_pending_reset_watermarks_uniqueness_index():
    indexes = {index.name: index for index in ReprocessingJob.__table__.indexes}

    uniqueness_index = indexes["uq_reprocessing_jobs_pending_reset_watermarks_security"]

    assert uniqueness_index.unique is True
    assert str(next(iter(uniqueness_index.expressions))) == "(payload->>'security_id')"
    assert (
        str(uniqueness_index.dialect_options["postgresql"]["where"])
        == "job_type = 'RESET_WATERMARKS' AND status = 'PENDING'"
    )


def test_analytics_export_job_declares_hot_path_indexes():
    indexes = {index.name: index for index in AnalyticsExportJob.__table__.indexes}

    portfolio_status_created = indexes["ix_analytics_export_jobs_portfolio_status_created_at"]
    status_updated = indexes["ix_analytics_export_jobs_status_updated_at"]

    assert [column.name for column in portfolio_status_created.columns] == [
        "portfolio_id",
        "status",
        "created_at",
    ]
    assert [column.name for column in status_updated.columns] == ["status", "updated_at"]


def test_portfolio_valuation_job_declares_operations_hot_path_indexes():
    indexes = {index.name: index for index in PortfolioValuationJob.__table__.indexes}

    portfolio_status_updated = indexes["ix_portfolio_valuation_jobs_portfolio_status_updated"]
    portfolio_status_date_updated = indexes[
        "ix_portfolio_valuation_jobs_portfolio_status_date_updated_id"
    ]

    assert [column.name for column in portfolio_status_updated.columns] == [
        "portfolio_id",
        "status",
        "updated_at",
    ]
    assert [column.name for column in portfolio_status_date_updated.columns] == [
        "portfolio_id",
        "status",
        "valuation_date",
        "updated_at",
        "id",
    ]


def test_portfolio_aggregation_job_declares_operations_hot_path_indexes():
    indexes = {index.name: index for index in PortfolioAggregationJob.__table__.indexes}

    portfolio_status_updated = indexes["ix_portfolio_aggregation_jobs_portfolio_status_updated"]
    portfolio_status_date_updated = indexes[
        "ix_portfolio_aggregation_jobs_portfolio_status_date_updated_id"
    ]

    assert [column.name for column in portfolio_status_updated.columns] == [
        "portfolio_id",
        "status",
        "updated_at",
    ]
    assert [column.name for column in portfolio_status_date_updated.columns] == [
        "portfolio_id",
        "status",
        "aggregation_date",
        "updated_at",
        "id",
    ]
