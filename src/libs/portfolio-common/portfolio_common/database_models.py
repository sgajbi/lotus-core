# libs/portfolio-common/portfolio_common/database_models.py
from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    Date,
    func,
    ForeignKey,
    UniqueConstraint,
    Boolean,
    JSON,
    Index,
    Text,
)
from sqlalchemy.orm import relationship

from .db_base import Base


class BusinessDate(Base):
    __tablename__ = "business_dates"

    date = Column(Date, primary_key=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, unique=True, index=True, nullable=False)
    base_currency = Column(String(3), nullable=False)
    open_date = Column(Date, nullable=False)
    close_date = Column(Date, nullable=True)
    risk_exposure = Column(String, nullable=False)
    investment_time_horizon = Column(String, nullable=False)
    portfolio_type = Column(String, nullable=False)
    objective = Column(String, nullable=True)
    booking_center_code = Column(String, nullable=False)
    client_id = Column(String, index=True, nullable=False)
    is_leverage_allowed = Column(Boolean, default=False, nullable=False)
    advisor_id = Column(String, nullable=True)
    status = Column(String, nullable=False)
    cost_basis_method = Column(String, server_default="FIFO", nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SimulationSession(Base):
    __tablename__ = "simulation_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), index=True, nullable=False)
    status = Column(String, nullable=False, server_default="ACTIVE")
    version = Column(Integer, nullable=False, server_default="1")
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SimulationChange(Base):
    __tablename__ = "simulation_changes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    change_id = Column(String, unique=True, index=True, nullable=False)
    session_id = Column(
        String, ForeignKey("simulation_sessions.session_id"), index=True, nullable=False
    )
    portfolio_id = Column(String, index=True, nullable=False)
    security_id = Column(String, index=True, nullable=False)
    transaction_type = Column(String, nullable=False)
    quantity = Column(Numeric(18, 10), nullable=True)
    price = Column(Numeric(18, 10), nullable=True)
    amount = Column(Numeric(18, 10), nullable=True)
    currency = Column(String, nullable=True)
    effective_date = Column(Date, nullable=True)
    change_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PositionHistory(Base):
    __tablename__ = "position_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), index=True, nullable=False)
    security_id = Column(String, index=True, nullable=False)
    transaction_id = Column(String, ForeignKey("transactions.transaction_id"), nullable=False)
    position_date = Column(Date, index=True, nullable=False)
    epoch = Column(Integer, nullable=False, default=0, server_default="0")
    quantity = Column(Numeric(18, 10), nullable=False)
    cost_basis = Column(Numeric(18, 10), nullable=False)
    cost_basis_local = Column(Numeric(18, 10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DailyPositionSnapshot(Base):
    __tablename__ = "daily_position_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), index=True, nullable=False)
    security_id = Column(String, index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    epoch = Column(Integer, nullable=False, default=0, server_default="0")
    quantity = Column(Numeric(18, 10), nullable=False)
    cost_basis = Column(Numeric(18, 10), nullable=False)
    cost_basis_local = Column(Numeric(18, 10), nullable=True)
    market_price = Column(Numeric(18, 10), nullable=True)
    market_value = Column(Numeric(18, 10), nullable=True)
    market_value_local = Column(Numeric(18, 10), nullable=True)
    unrealized_gain_loss = Column(Numeric(18, 10), nullable=True)
    unrealized_gain_loss_local = Column(Numeric(18, 10), nullable=True)
    valuation_status = Column(String, nullable=False, server_default="UNVALUED", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "security_id", "date", "epoch", name="_portfolio_security_date_epoch_uc"
        ),
        Index(
            "ix_daily_position_snapshots_covering",
            "portfolio_id",
            "security_id",
            date.desc(),
            id.desc(),
        ),
    )


class FxRate(Base):
    __tablename__ = "fx_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    rate_date = Column(Date, nullable=False)
    rate = Column(Numeric(18, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "from_currency", "to_currency", "rate_date", name="_currency_pair_date_uc"
        ),
    )


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    security_id = Column(String, index=True, nullable=False)
    price_date = Column(Date, nullable=False)
    price = Column(Numeric(18, 10), nullable=False)
    currency = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("security_id", "price_date", name="_security_price_date_uc"),
    )


class Instrument(Base):
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    security_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    isin = Column(String, unique=True, nullable=False)
    currency = Column(String, nullable=False)
    product_type = Column(String, nullable=False)
    asset_class = Column(String, nullable=True)
    sector = Column(String, nullable=True)
    country_of_risk = Column(String, nullable=True)
    rating = Column(String, nullable=True)
    maturity_date = Column(Date, nullable=True)
    issuer_id = Column(String, nullable=True, index=True)
    issuer_name = Column(String, nullable=True)
    ultimate_parent_issuer_id = Column(String, nullable=True, index=True)
    ultimate_parent_issuer_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PortfolioBenchmarkAssignment(Base):
    __tablename__ = "portfolio_benchmark_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    benchmark_id = Column(String, nullable=False, index=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    assignment_source = Column(String, nullable=False)
    assignment_status = Column(String, nullable=False, server_default="active", index=True)
    policy_pack_id = Column(String, nullable=True)
    source_system = Column(String, nullable=True)
    assignment_recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    assignment_version = Column(Integer, nullable=False, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "benchmark_id",
            "effective_from",
            "assignment_version",
            name="_portfolio_benchmark_assignment_uc",
        ),
    )


class BenchmarkDefinition(Base):
    __tablename__ = "benchmark_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    benchmark_id = Column(String, nullable=False, index=True)
    benchmark_name = Column(String, nullable=False)
    benchmark_type = Column(String, nullable=False)
    benchmark_currency = Column(String(3), nullable=False)
    return_convention = Column(String, nullable=False)
    benchmark_status = Column(String, nullable=False, server_default="active", index=True)
    benchmark_family = Column(String, nullable=True)
    benchmark_provider = Column(String, nullable=True)
    rebalance_frequency = Column(String, nullable=True)
    classification_set_id = Column(String, nullable=True)
    classification_labels = Column(JSON, nullable=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_vendor = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "benchmark_id",
            "effective_from",
            name="_benchmark_definition_effective_uc",
        ),
    )


class IndexDefinition(Base):
    __tablename__ = "index_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    index_id = Column(String, nullable=False, index=True)
    index_name = Column(String, nullable=False)
    index_currency = Column(String(3), nullable=False)
    index_type = Column(String, nullable=True)
    index_status = Column(String, nullable=False, server_default="active", index=True)
    index_provider = Column(String, nullable=True)
    index_market = Column(String, nullable=True)
    classification_set_id = Column(String, nullable=True)
    classification_labels = Column(JSON, nullable=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_vendor = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("index_id", "effective_from", name="_index_definition_effective_uc"),
    )


class BenchmarkCompositionSeries(Base):
    __tablename__ = "benchmark_composition_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    benchmark_id = Column(String, nullable=False, index=True)
    index_id = Column(String, nullable=False, index=True)
    composition_effective_from = Column(Date, nullable=False, index=True)
    composition_effective_to = Column(Date, nullable=True, index=True)
    composition_weight = Column(Numeric(18, 10), nullable=False)
    rebalance_event_id = Column(String, nullable=True, index=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_vendor = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "benchmark_id",
            "index_id",
            "composition_effective_from",
            name="_benchmark_composition_effective_uc",
        ),
    )


class IndexPriceSeries(Base):
    __tablename__ = "index_price_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(String, nullable=False, index=True)
    index_id = Column(String, nullable=False, index=True)
    series_date = Column(Date, nullable=False, index=True)
    index_price = Column(Numeric(18, 10), nullable=False)
    series_currency = Column(String(3), nullable=False)
    value_convention = Column(String, nullable=False)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_vendor = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("series_id", "index_id", "series_date", name="_index_price_series_uc"),
    )


class IndexReturnSeries(Base):
    __tablename__ = "index_return_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(String, nullable=False, index=True)
    index_id = Column(String, nullable=False, index=True)
    series_date = Column(Date, nullable=False, index=True)
    index_return = Column(Numeric(18, 10), nullable=False)
    return_period = Column(String, nullable=False)
    return_convention = Column(String, nullable=False)
    series_currency = Column(String(3), nullable=False)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_vendor = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("series_id", "index_id", "series_date", name="_index_return_series_uc"),
    )


class BenchmarkReturnSeries(Base):
    __tablename__ = "benchmark_return_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(String, nullable=False, index=True)
    benchmark_id = Column(String, nullable=False, index=True)
    series_date = Column(Date, nullable=False, index=True)
    benchmark_return = Column(Numeric(18, 10), nullable=False)
    return_period = Column(String, nullable=False)
    return_convention = Column(String, nullable=False)
    series_currency = Column(String(3), nullable=False)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_vendor = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "series_id",
            "benchmark_id",
            "series_date",
            name="_benchmark_return_series_uc",
        ),
    )


class RiskFreeSeries(Base):
    __tablename__ = "risk_free_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(String, nullable=False, index=True)
    risk_free_curve_id = Column(String, nullable=False, index=True)
    series_date = Column(Date, nullable=False, index=True)
    value = Column(Numeric(18, 10), nullable=False)
    value_convention = Column(String, nullable=False)
    day_count_convention = Column(String, nullable=True)
    compounding_convention = Column(String, nullable=True)
    series_currency = Column(String(3), nullable=False, index=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_vendor = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "series_id",
            "risk_free_curve_id",
            "series_date",
            name="_risk_free_series_uc",
        ),
    )


class ClassificationTaxonomy(Base):
    __tablename__ = "classification_taxonomy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    classification_set_id = Column(String, nullable=False, index=True)
    taxonomy_scope = Column(String, nullable=False, index=True)
    dimension_name = Column(String, nullable=False, index=True)
    dimension_value = Column(String, nullable=False, index=True)
    dimension_description = Column(String, nullable=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_vendor = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "classification_set_id",
            "taxonomy_scope",
            "dimension_name",
            "dimension_value",
            "effective_from",
            name="_classification_taxonomy_effective_uc",
        ),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, unique=True, index=True, nullable=False)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False)
    instrument_id = Column(String, nullable=False)
    security_id = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)
    quantity = Column(Numeric(18, 10), nullable=False)
    price = Column(Numeric(18, 10), nullable=False)
    gross_transaction_amount = Column(Numeric(18, 10), nullable=False)
    trade_currency = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    settlement_date = Column(DateTime(timezone=True), nullable=True)
    trade_fee = Column(Numeric(18, 10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    gross_cost = Column(Numeric(18, 10), nullable=True)
    net_cost = Column(Numeric(18, 10), nullable=True)
    realized_gain_loss = Column(Numeric(18, 10), nullable=True)
    transaction_fx_rate = Column(Numeric(18, 10), nullable=True)
    net_cost_local = Column(Numeric(18, 10), nullable=True)
    realized_gain_loss_local = Column(Numeric(18, 10), nullable=True)
    economic_event_id = Column(String, nullable=True, index=True)
    linked_transaction_group_id = Column(String, nullable=True, index=True)
    calculation_policy_id = Column(String, nullable=True)
    calculation_policy_version = Column(String, nullable=True)
    source_system = Column(String, nullable=True)

    costs = relationship(
        "TransactionCost", back_populates="transaction", cascade="all, delete-orphan"
    )
    cashflow = relationship(
        "Cashflow", uselist=False, back_populates="transaction", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_transactions_portfolio_security", "portfolio_id", "security_id"),)


class TransactionCost(Base):
    __tablename__ = "transaction_costs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, ForeignKey("transactions.transaction_id"), nullable=False)
    fee_type = Column(String, nullable=False)
    amount = Column(Numeric(18, 10), nullable=False)
    currency = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    transaction = relationship("Transaction", back_populates="costs")


class Cashflow(Base):
    __tablename__ = "cashflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, ForeignKey("transactions.transaction_id"), nullable=False)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), index=True, nullable=False)
    security_id = Column(String, index=True, nullable=True)
    cashflow_date = Column(Date, index=True, nullable=False)
    epoch = Column(Integer, nullable=False, default=0, server_default="0")
    amount = Column(Numeric(18, 10), nullable=False)
    currency = Column(String(3), nullable=False)
    classification = Column(String, nullable=False)
    timing = Column(String, nullable=False)
    calculation_type = Column(String, nullable=False)
    is_position_flow = Column(Boolean, server_default="f", nullable=False)
    is_portfolio_flow = Column(Boolean, server_default="f", nullable=False)
    economic_event_id = Column(String, nullable=True, index=True)
    linked_transaction_group_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    transaction = relationship("Transaction", back_populates="cashflow")

    __table_args__ = (UniqueConstraint("transaction_id", name="_transaction_id_uc"),)


class PositionLotState(Base):
    __tablename__ = "position_lot_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lot_id = Column(String, unique=True, index=True, nullable=False)
    source_transaction_id = Column(
        String, ForeignKey("transactions.transaction_id"), nullable=False, unique=True
    )
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), index=True, nullable=False)
    instrument_id = Column(String, nullable=False, index=True)
    security_id = Column(String, nullable=False, index=True)
    acquisition_date = Column(Date, nullable=False, index=True)
    original_quantity = Column(Numeric(18, 10), nullable=False)
    open_quantity = Column(Numeric(18, 10), nullable=False)
    lot_cost_local = Column(Numeric(18, 10), nullable=False)
    lot_cost_base = Column(Numeric(18, 10), nullable=False)
    accrued_interest_paid_local = Column(Numeric(18, 10), nullable=False, server_default="0")
    economic_event_id = Column(String, nullable=True, index=True)
    linked_transaction_group_id = Column(String, nullable=True, index=True)
    calculation_policy_id = Column(String, nullable=True)
    calculation_policy_version = Column(String, nullable=True)
    source_system = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AccruedIncomeOffsetState(Base):
    __tablename__ = "accrued_income_offset_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    offset_id = Column(String, unique=True, index=True, nullable=False)
    source_transaction_id = Column(
        String, ForeignKey("transactions.transaction_id"), nullable=False, unique=True
    )
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), index=True, nullable=False)
    instrument_id = Column(String, nullable=False, index=True)
    security_id = Column(String, nullable=False, index=True)
    accrued_interest_paid_local = Column(Numeric(18, 10), nullable=False, server_default="0")
    remaining_offset_local = Column(Numeric(18, 10), nullable=False, server_default="0")
    economic_event_id = Column(String, nullable=True, index=True)
    linked_transaction_group_id = Column(String, nullable=True, index=True)
    calculation_policy_id = Column(String, nullable=True)
    calculation_policy_version = Column(String, nullable=True)
    source_system = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PositionTimeseries(Base):
    __tablename__ = "position_timeseries"

    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), primary_key=True)
    security_id = Column(String, ForeignKey("instruments.security_id"), primary_key=True)
    date = Column(Date, primary_key=True)
    epoch = Column(Integer, primary_key=True, default=0, server_default="0")
    bod_market_value = Column(Numeric(18, 10), nullable=False)
    bod_cashflow_position = Column(Numeric(18, 10), nullable=False)
    eod_cashflow_position = Column(Numeric(18, 10), nullable=False)
    bod_cashflow_portfolio = Column(Numeric(18, 10), nullable=False)
    eod_cashflow_portfolio = Column(Numeric(18, 10), nullable=False)
    eod_market_value = Column(Numeric(18, 10), nullable=False)
    fees = Column(Numeric(18, 10), default=0, nullable=False)
    quantity = Column(Numeric(18, 10), nullable=False)
    cost = Column(Numeric(18, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PortfolioTimeseries(Base):
    __tablename__ = "portfolio_timeseries"

    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), primary_key=True)
    date = Column(Date, primary_key=True)
    epoch = Column(Integer, primary_key=True, default=0, server_default="0")
    bod_market_value = Column(Numeric(18, 10), nullable=False)
    bod_cashflow = Column(Numeric(18, 10), nullable=False)
    eod_cashflow = Column(Numeric(18, 10), nullable=False)
    eod_market_value = Column(Numeric(18, 10), nullable=False)
    fees = Column(Numeric(18, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def to_dict(self):
        """Converts the object to a dictionary."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, nullable=False)
    portfolio_id = Column(String, nullable=False)
    service_name = Column(String, nullable=False)
    correlation_id = Column(String, nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("event_id", "service_name", name="_event_service_uc"),)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    aggregate_type = Column(String, nullable=False, index=True)
    aggregate_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    topic = Column(String, nullable=False)
    status = Column(String, default="PENDING", nullable=False, index=True)
    correlation_id = Column(String, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    last_attempted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)


class PortfolioAggregationJob(Base):
    """
    Tracks portfolio-date pairs that require aggregation.
    This table acts as a stateful, idempotent queue to trigger portfolio time series calculations.
    """

    __tablename__ = "portfolio_aggregation_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, nullable=False, index=True)
    aggregation_date = Column(Date, nullable=False, index=True)
    status = Column(String, nullable=False, default="PENDING", index=True)
    correlation_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("portfolio_id", "aggregation_date", name="_portfolio_date_uc"),
    )


class PortfolioValuationJob(Base):
    """
    Tracks portfolio-security-date combinations that require valuation.
    This table acts as a stateful, idempotent work set to trigger valuation calculations,
    preventing race conditions from multiple upstream events.
    """

    __tablename__ = "portfolio_valuation_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, nullable=False, index=True)
    security_id = Column(String, nullable=False, index=True)
    valuation_date = Column(Date, nullable=False, index=True)
    epoch = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String, nullable=False, default="PENDING", index=True)
    correlation_id = Column(String, nullable=True)
    failure_reason = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "security_id",
            "valuation_date",
            "epoch",
            name="_portfolio_security_valuation_date_epoch_uc",
        ),
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, unique=True, index=True, nullable=False)
    endpoint = Column(String, index=True, nullable=False)
    entity_type = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False, server_default="accepted")
    accepted_count = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=True, index=True)
    correlation_id = Column(String, nullable=False)
    request_id = Column(String, nullable=False)
    trace_id = Column(String, nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)
    request_payload = Column(JSON, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_retried_at = Column(DateTime(timezone=True), nullable=True)


class IngestionJobFailure(Base):
    __tablename__ = "ingestion_job_failures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    failure_id = Column(String, unique=True, index=True, nullable=False)
    job_id = Column(String, ForeignKey("ingestion_jobs.job_id"), index=True, nullable=False)
    failure_phase = Column(String, nullable=False)
    failure_reason = Column(Text, nullable=False)
    failed_record_keys = Column(JSON, nullable=True)
    failed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IngestionOpsControl(Base):
    __tablename__ = "ingestion_ops_control"

    id = Column(Integer, primary_key=True, autoincrement=False)
    mode = Column(String, nullable=False, server_default="normal")
    replay_window_start = Column(DateTime(timezone=True), nullable=True)
    replay_window_end = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConsumerDlqEvent(Base):
    __tablename__ = "consumer_dlq_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, unique=True, index=True, nullable=False)
    original_topic = Column(String, index=True, nullable=False)
    consumer_group = Column(String, index=True, nullable=False)
    dlq_topic = Column(String, index=True, nullable=False)
    original_key = Column(String, nullable=True)
    error_reason = Column(Text, nullable=False)
    correlation_id = Column(String, nullable=True)
    payload_excerpt = Column(Text, nullable=True)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConsumerDlqReplayAudit(Base):
    __tablename__ = "consumer_dlq_replay_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    replay_id = Column(String, unique=True, index=True, nullable=False)
    recovery_path = Column(String, nullable=False, server_default="consumer_dlq_replay", index=True)
    event_id = Column(String, index=True, nullable=False)
    replay_fingerprint = Column(String, index=True, nullable=False)
    correlation_id = Column(String, nullable=True)
    job_id = Column(String, nullable=True, index=True)
    endpoint = Column(String, nullable=True)
    replay_status = Column(String, nullable=False, index=True)
    dry_run = Column(Boolean, nullable=False, server_default="f")
    replay_reason = Column(Text, nullable=False)
    requested_by = Column(String, nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class PositionState(Base):
    """
    Tracks the current reprocessing state (epoch and watermark) for each portfolio-security key.
    """

    __tablename__ = "position_state"

    portfolio_id = Column(String, primary_key=True)
    security_id = Column(String, primary_key=True)
    epoch = Column(Integer, nullable=False, server_default="0")
    watermark_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, server_default="CURRENT", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InstrumentReprocessingState(Base):
    """
    A state table to track back-dated price events for an instrument.
    This acts as a trigger for the ValuationScheduler to find and update
    all affected PositionState watermarks.
    """

    __tablename__ = "instrument_reprocessing_state"

    security_id = Column(String, primary_key=True)
    earliest_impacted_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReprocessingJob(Base):
    """
    Stores durable, persistent jobs for the reprocessing engine,
    such as fanning out watermark resets for a price change.
    """

    __tablename__ = "reprocessing_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default="PENDING", index=True)

    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_attempted_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AnalyticsExportJob(Base):
    __tablename__ = "analytics_export_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, unique=True, index=True, nullable=False)
    dataset_type = Column(String, index=True, nullable=False)
    portfolio_id = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False, server_default="accepted")
    request_fingerprint = Column(String, index=True, nullable=False)
    request_payload = Column(JSON, nullable=False)
    result_payload = Column(JSON, nullable=True)
    result_row_count = Column(Integer, nullable=True)
    result_format = Column(String, nullable=False, server_default="json")
    compression = Column(String, nullable=False, server_default="none")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

class CashflowRule(Base):
    """
    Defines the business rules for generating a cashflow from a transaction type.
    """

    __tablename__ = "cashflow_rules"

    transaction_type = Column(String(50), primary_key=True)
    classification = Column(String(50), nullable=False)
    timing = Column(String(10), nullable=False)
    is_position_flow = Column(Boolean, nullable=False)
    is_portfolio_flow = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
