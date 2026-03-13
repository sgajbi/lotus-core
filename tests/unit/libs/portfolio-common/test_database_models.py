from portfolio_common.database_models import AnalyticsExportJob, ReprocessingJob


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
