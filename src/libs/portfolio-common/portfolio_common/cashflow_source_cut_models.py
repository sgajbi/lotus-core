"""Persistence model for the transactionally maintained cashflow source cut."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String

from .database_models import Base


class PortfolioCashflowSourceCut(Base):
    """Durable, source-owned replay evidence for one portfolio cashflow cut.

    PostgreSQL maintains this projection transactionally from ``cashflows`` and
    ``transactions``. Query products read its fixed-width values rather than
    re-hashing the portfolio's complete history on every request.
    """

    __tablename__ = "portfolio_cashflow_source_cuts"

    portfolio_id = Column(
        String,
        ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
        primary_key=True,
    )
    portfolio_base_currency = Column(String(3), nullable=False)
    cashflow_revision_count = Column(BigInteger, nullable=False)
    cashflow_revision_digest = Column(String(64), nullable=False)
    settlement_revision_count = Column(BigInteger, nullable=False)
    settlement_revision_digest = Column(String(64), nullable=False)
    materialized_at = Column(DateTime(timezone=True), nullable=False)


class PortfolioCashflowSourceCutRefreshQueue(Base):
    """Per-transaction work queue for deferred source-cut materialization.

    Transaction processing stages each affected portfolio once, then flushes
    this durable queue immediately before its atomic commit.  Keeping the
    table in Alembic metadata prevents an autogeneration from proposing to
    remove a live trigger dependency.
    """

    __tablename__ = "portfolio_cashflow_source_cut_refresh_queue"

    transaction_id = Column(BigInteger, primary_key=True)
    portfolio_id = Column(
        String,
        ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
        primary_key=True,
    )
