# libs/portfolio-common/portfolio_common/database_models.py
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .db_base import Base
from .domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from .financial_numeric import ExactNumeric
from .source_lifecycle_predicates import (
    BENCHMARK_DEFINITION_ACTIVE,
    CLIENT_INCOME_NEEDS_ACTIVE,
    CLIENT_RESTRICTION_ACTIVE,
    CLIENT_TAX_PROFILE_ACTIVE,
    CLIENT_TAX_RULE_SET_ACTIVE,
    DPM_DISCRETIONARY_MANDATE_ACTIVE,
    INDEX_DEFINITION_ACTIVE,
    LIQUIDITY_RESERVE_ACTIVE,
    MODEL_PORTFOLIO_TARGET_ACTIVE,
    PLANNED_WITHDRAWAL_ACTIVE,
    SUSTAINABILITY_PREFERENCE_ACTIVE,
)

_POSTGRESQL_SPECIAL_NUMERIC_VALUES = ("NaN", "Infinity", "-Infinity")


def _finite_numeric_check_constraint(
    name: str,
    *column_names: str,
) -> CheckConstraint:
    """Build one explicit PostgreSQL finite-value check for numeric columns."""

    if not column_names:
        raise ValueError("at least one numeric column is required")
    if any(not column_name.isidentifier() for column_name in column_names):
        raise ValueError("numeric column names must be identifiers")
    special_values = ", ".join(f"'{value}'" for value in _POSTGRESQL_SPECIAL_NUMERIC_VALUES)
    condition = " AND ".join(
        f"CAST({column_name} AS TEXT) NOT IN ({special_values})" for column_name in column_names
    )
    return CheckConstraint(condition, name=name)


class BusinessDate(Base):
    __tablename__ = "business_dates"

    calendar_code = Column(
        String, primary_key=True, nullable=False, default="GLOBAL", server_default="GLOBAL"
    )
    date = Column(Date, primary_key=True, nullable=False)
    market_code = Column(String, nullable=True)
    source_system = Column(String, nullable=True)
    source_batch_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, unique=True, index=True, nullable=False)
    tenant_id = Column(String, nullable=True)
    legal_book_id = Column(String, nullable=True)
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

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            name="uq_portfolios_book_scope_identity",
        ),
        CheckConstraint(
            "(tenant_id IS NULL AND legal_book_id IS NULL) OR "
            "(tenant_id IS NOT NULL AND legal_book_id IS NOT NULL "
            "AND tenant_id = btrim(tenant_id) AND legal_book_id = btrim(legal_book_id) "
            "AND tenant_id <> '' AND legal_book_id <> '')",
            name="ck_portfolios_valuation_book_scope_complete",
        ),
        Index("ix_portfolios_booking_center_code", "booking_center_code"),
        Index("ix_portfolios_norm_portfolio_id", func.trim(portfolio_id)),
        Index(
            "ix_portfolios_advisor_status_open_close_portfolio",
            "advisor_id",
            "status",
            "open_date",
            "close_date",
            "portfolio_id",
        ),
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
    quantity = Column(ExactNumeric(18, 10), nullable=True)
    price = Column(ExactNumeric(18, 10), nullable=True)
    amount = Column(ExactNumeric(18, 10), nullable=True)
    currency = Column(String, nullable=True)
    effective_date = Column(Date, nullable=True)
    change_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_simulation_change_values_finite",
            "quantity",
            "price",
            "amount",
        ),
        CheckConstraint(
            "price > 0",
            name="ck_simulation_change_price_positive",
        ),
    )


class PositionHistory(Base):
    __tablename__ = "position_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), index=True, nullable=False)
    security_id = Column(String, index=True, nullable=False)
    transaction_id = Column(String, ForeignKey("transactions.transaction_id"), nullable=False)
    position_date = Column(Date, index=True, nullable=False)
    epoch = Column(Integer, nullable=False, default=0, server_default="0")
    quantity = Column(ExactNumeric(18, 10), nullable=False)
    cost_basis = Column(ExactNumeric(18, 10), nullable=False)
    cost_basis_local = Column(ExactNumeric(18, 10), nullable=True)
    calculation_lineage = Column(JSON(none_as_null=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_position_history_values_finite",
            "quantity",
            "cost_basis",
            "cost_basis_local",
        ),
        Index(
            "ix_position_history_portfolio_security_epoch_date",
            "portfolio_id",
            "security_id",
            "epoch",
            "position_date",
        ),
        Index(
            "ix_position_history_security_epoch_date_id_portfolio",
            "security_id",
            "epoch",
            position_date.desc(),
            id.desc(),
            "portfolio_id",
        ),
        Index(
            "ix_pos_hist_norm_port_sec_epoch_date",
            func.trim(portfolio_id),
            func.trim(security_id),
            "epoch",
            position_date.desc(),
            id.desc(),
        ),
        Index(
            "ix_pos_hist_norm_port_sec_epoch_txn",
            func.trim(portfolio_id),
            func.trim(security_id),
            "epoch",
            func.trim(transaction_id),
        ),
        Index(
            "ix_pos_hist_port_norm_sec_date_id",
            "portfolio_id",
            func.trim(security_id),
            position_date.desc(),
            id.desc(),
            "epoch",
        ),
        Index(
            "ix_pos_hist_lineage_latest",
            "portfolio_id",
            func.trim(security_id),
            "epoch",
            position_date.desc(),
        ),
    )


class DailyPositionSnapshot(Base):
    __tablename__ = "daily_position_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), index=True, nullable=False)
    security_id = Column(String, index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    epoch = Column(Integer, nullable=False, default=0, server_default="0")
    quantity = Column(ExactNumeric(18, 10), nullable=False)
    cost_basis = Column(ExactNumeric(18, 10), nullable=False)
    cost_basis_local = Column(ExactNumeric(18, 10), nullable=True)
    market_price = Column(ExactNumeric(18, 10), nullable=True)
    market_value = Column(ExactNumeric(18, 10), nullable=True)
    market_value_local = Column(ExactNumeric(18, 10), nullable=True)
    unrealized_gain_loss = Column(ExactNumeric(18, 10), nullable=True)
    unrealized_gain_loss_local = Column(ExactNumeric(18, 10), nullable=True)
    unrealized_price_gain_loss = Column(ExactNumeric(18, 10), nullable=True)
    unrealized_fx_gain_loss = Column(ExactNumeric(18, 10), nullable=True)
    valuation_status = Column(String, nullable=False, server_default="UNVALUED", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_daily_position_snapshot_values_finite",
            "quantity",
            "cost_basis",
            "cost_basis_local",
            "market_price",
            "market_value",
            "market_value_local",
            "unrealized_gain_loss",
            "unrealized_gain_loss_local",
            "unrealized_price_gain_loss",
            "unrealized_fx_gain_loss",
        ),
        CheckConstraint(
            "market_price > 0",
            name="ck_daily_position_snapshot_price_positive",
        ),
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
        Index(
            "ix_daily_snap_norm_port_sec_date_epoch",
            func.trim(portfolio_id),
            func.trim(security_id),
            date.desc(),
            epoch.desc(),
        ),
        Index(
            "ix_daily_snap_port_norm_sec_date_id",
            "portfolio_id",
            func.trim(security_id),
            date.desc(),
            id.desc(),
            "epoch",
        ),
        Index(
            "ix_daily_snap_lineage_latest",
            "portfolio_id",
            func.trim(security_id),
            "epoch",
            date.desc(),
        ),
        Index(
            "ix_daily_snap_port_date_status_norm_sec_epoch",
            "portfolio_id",
            "date",
            "valuation_status",
            func.trim(security_id),
            "epoch",
        ),
    )


class DailyPositionValuationReceiptRecord(Base):
    """One durable calculation/supportability receipt per position snapshot."""

    __tablename__ = "daily_position_valuation_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(
        Integer,
        ForeignKey("daily_position_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    supportability = Column(String, nullable=False)
    supportability_reasons = Column(JSON, nullable=False)
    policy_id = Column(String, nullable=True)
    policy_version = Column(Integer, nullable=True)
    assignment_version = Column(Integer, nullable=True)
    assignment_content_hash = Column(String(64), nullable=True)
    policy_assignment_source = Column(JSON(none_as_null=True), nullable=True)
    quote_basis = Column(String, nullable=True)
    price_fact_version = Column(Integer, nullable=True)
    price_fact_content_hash = Column(String(64), nullable=True)
    market_price_source = Column(JSON(none_as_null=True), nullable=True)
    calculation_lineage = Column(JSON(none_as_null=True), nullable=True)
    receipt_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "supportability IN ('SUPPORTED', 'LEGACY_UNSCOPED')",
            name="ck_daily_position_valuation_receipt_supportability",
        ),
        CheckConstraint(
            "json_array_length(supportability_reasons) > 0",
            name="ck_daily_position_valuation_receipt_reasons_nonempty",
        ),
        CheckConstraint(
            "("
            "supportability = 'SUPPORTED' "
            "AND policy_id IS NOT NULL AND btrim(policy_id) <> '' "
            "AND policy_version >= 1 AND assignment_version >= 1 "
            "AND assignment_content_hash IS NOT NULL "
            "AND policy_assignment_source IS NOT NULL "
            "AND quote_basis IS NOT NULL "
            "AND price_fact_version >= 1 AND price_fact_content_hash IS NOT NULL "
            "AND market_price_source IS NOT NULL AND calculation_lineage IS NOT NULL"
            ") OR ("
            "supportability = 'LEGACY_UNSCOPED' "
            "AND policy_id IS NULL AND policy_version IS NULL "
            "AND assignment_version IS NULL AND assignment_content_hash IS NULL "
            "AND policy_assignment_source IS NULL AND quote_basis IS NULL "
            "AND price_fact_version IS NULL AND price_fact_content_hash IS NULL "
            "AND market_price_source IS NULL"
            ")",
            name="ck_daily_position_valuation_receipt_evidence_complete",
        ),
        CheckConstraint(
            "assignment_content_hash IS NULL OR assignment_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_daily_position_valuation_receipt_assignment_hash",
        ),
        CheckConstraint(
            "price_fact_content_hash IS NULL OR price_fact_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_daily_position_valuation_receipt_price_hash",
        ),
        CheckConstraint(
            "receipt_hash ~ '^[0-9a-f]{64}$'",
            name="ck_daily_position_valuation_receipt_hash",
        ),
        Index(
            "ix_daily_position_valuation_receipt_supportability_snapshot",
            "supportability",
            "snapshot_id",
        ),
    )


class FxRate(Base):
    __tablename__ = "fx_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    rate_date = Column(Date, nullable=False)
    rate = Column(ExactNumeric(18, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_fx_rates_rate_finite",
            "rate",
        ),
        CheckConstraint(
            "rate > 0",
            name="ck_fx_rates_rate_positive",
        ),
        UniqueConstraint(
            "from_currency", "to_currency", "rate_date", name="_currency_pair_date_uc"
        ),
        Index(
            "ix_fx_rates_normalized_pair_rate_date",
            func.upper(func.trim(from_currency)),
            func.upper(func.trim(to_currency)),
            rate_date.desc(),
        ),
    )


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    security_id = Column(String, index=True, nullable=False)
    price_date = Column(Date, nullable=False)
    price = Column(ExactNumeric(18, 10), nullable=False)
    currency = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_market_prices_price_finite",
            "price",
        ),
        CheckConstraint(
            "price > 0",
            name="ck_market_prices_price_positive",
        ),
        UniqueConstraint("security_id", "price_date", name="_security_price_date_uc"),
        Index(
            "ix_market_prices_norm_sec_price_date",
            func.trim(security_id),
            price_date.desc(),
        ),
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
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=True, index=True)
    trade_date = Column(Date, nullable=True)
    pair_base_currency = Column(String(3), nullable=True)
    pair_quote_currency = Column(String(3), nullable=True)
    buy_currency = Column(String(3), nullable=True)
    sell_currency = Column(String(3), nullable=True)
    buy_amount = Column(ExactNumeric(18, 10), nullable=True)
    sell_amount = Column(ExactNumeric(18, 10), nullable=True)
    contract_rate = Column(ExactNumeric(18, 10), nullable=True)
    sector = Column(String, nullable=True)
    country_of_risk = Column(String, nullable=True)
    rating = Column(String, nullable=True)
    liquidity_tier = Column(String, nullable=True)
    maturity_date = Column(Date, nullable=True)
    issuer_id = Column(String, nullable=True, index=True)
    issuer_name = Column(String, nullable=True)
    ultimate_parent_issuer_id = Column(String, nullable=True, index=True)
    ultimate_parent_issuer_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_instruments_fx_terms_finite",
            "buy_amount",
            "sell_amount",
            "contract_rate",
        ),
        CheckConstraint(
            "buy_amount > 0 AND sell_amount > 0 AND contract_rate > 0",
            name="ck_instruments_fx_terms_positive",
        ),
        Index("ix_instruments_norm_security_id", func.trim(security_id)),
        Index(
            "ix_instruments_norm_asset_cls_sec",
            func.upper(func.trim(asset_class)),
            func.trim(security_id),
        ),
    )


class InstrumentValuationPolicyAssignmentRecord(Base):
    """Source-versioned assignment of one instrument to one valuation policy."""

    __tablename__ = "instrument_valuation_policy_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, nullable=False)
    legal_book_id = Column(String, nullable=False)
    security_id = Column(String, ForeignKey("instruments.security_id"), nullable=False)
    policy_id = Column(String, nullable=False)
    policy_version = Column(Integer, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    assignment_status = Column(String, nullable=False)
    assignment_version = Column(Integer, nullable=False)
    source_system = Column(String, nullable=False)
    source_record_id = Column(String, nullable=False)
    source_revision = Column(String, nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    assignment_reason = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "legal_book_id",
            "security_id",
            "source_system",
            "source_record_id",
            "assignment_version",
            name="uq_inst_val_policy_source_version",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_inst_val_policy_effective_window",
        ),
        CheckConstraint(
            "policy_version >= 1",
            name="ck_inst_val_policy_version_positive",
        ),
        CheckConstraint(
            "assignment_version >= 1",
            name="ck_inst_val_assignment_version_positive",
        ),
        CheckConstraint(
            "assignment_status IN ('ACTIVE', 'SUSPENDED', 'RETIRED')",
            name="ck_inst_val_assignment_status_governed",
        ),
        Index(
            "ix_inst_val_policy_scope_effective",
            "tenant_id",
            "legal_book_id",
            "security_id",
            "valid_from",
            "valid_to",
            postgresql_where=text("assignment_status = 'ACTIVE'"),
        ),
        Index(
            "ix_inst_val_policy_source_history",
            "tenant_id",
            "legal_book_id",
            "security_id",
            "source_system",
            "source_record_id",
            assignment_version.desc(),
        ),
    )


class MarketPriceSourceFactRecord(Base):
    """Append-history source-versioned authority for one scoped market-price fact."""

    __tablename__ = "market_price_source_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, nullable=False)
    legal_book_id = Column(String, nullable=False)
    security_id = Column(String, ForeignKey("instruments.security_id"), nullable=False)
    price_date = Column(Date, nullable=False)
    price = Column(ExactNumeric(), nullable=False)
    currency = Column(String(3), nullable=False)
    quote_basis = Column(String, nullable=False)
    fact_status = Column(String, nullable=False)
    fact_version = Column(Integer, nullable=False)
    source_system = Column(String, nullable=False)
    source_record_id = Column(String, nullable=False)
    source_revision = Column(String, nullable=False)
    source_content_hash = Column(String(64), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "source_record_id",
            "fact_version",
            name="uq_market_price_source_fact_version",
        ),
        CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' "
            "AND legal_book_id = btrim(legal_book_id) AND legal_book_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> ''",
            name="ck_market_price_source_fact_scope_normalized",
        ),
        CheckConstraint(
            "price > 0",
            name="ck_market_price_source_fact_price_positive",
        ),
        CheckConstraint(
            "price NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name="ck_market_price_source_fact_price_finite",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_market_price_source_fact_currency_normalized",
        ),
        CheckConstraint(
            "quote_basis IN "
            "('UNIT_PRICE', 'PERCENT_OF_PRINCIPAL_CLEAN', "
            "'PERCENT_OF_PRINCIPAL_DIRTY')",
            name="ck_market_price_source_fact_quote_basis",
        ),
        CheckConstraint(
            "fact_status IN ('ACTIVE', 'SUSPENDED', 'RETIRED')",
            name="ck_market_price_source_fact_status",
        ),
        CheckConstraint(
            "fact_version >= 1",
            name="ck_market_price_source_fact_version_positive",
        ),
        CheckConstraint(
            "source_system = btrim(source_system) AND source_system <> '' "
            "AND source_record_id = btrim(source_record_id) AND source_record_id <> '' "
            "AND source_revision = btrim(source_revision) AND source_revision <> ''",
            name="ck_market_price_source_fact_source_normalized",
        ),
        CheckConstraint(
            "source_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_market_price_source_fact_source_hash",
        ),
        CheckConstraint(
            "isfinite(observed_at)",
            name="ck_market_price_source_fact_observed_at_finite",
        ),
        Index(
            "ix_market_price_fact_scope_history",
            "tenant_id",
            "legal_book_id",
            "security_id",
            "price_date",
            "source_system",
            "source_record_id",
        ),
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
    assignment_recorded_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
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


class PortfolioMandateBinding(Base):
    __tablename__ = "portfolio_mandate_bindings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    mandate_id = Column(String, nullable=False, index=True)
    client_id = Column(String, nullable=False, index=True)
    mandate_type = Column(String, nullable=False, index=True)
    discretionary_authority_status = Column(String, nullable=False, index=True)
    booking_center_code = Column(String, nullable=False, index=True)
    jurisdiction_code = Column(String, nullable=False, index=True)
    model_portfolio_id = Column(String, nullable=False, index=True)
    policy_pack_id = Column(String, nullable=True, index=True)
    mandate_objective = Column(String, nullable=True)
    risk_profile = Column(String, nullable=False)
    investment_horizon = Column(String, nullable=False)
    review_cadence = Column(String, nullable=True)
    last_review_date = Column(Date, nullable=True)
    next_review_due_date = Column(Date, nullable=True)
    leverage_allowed = Column(Boolean, nullable=False, server_default="f")
    tax_awareness_allowed = Column(Boolean, nullable=False, server_default="f")
    settlement_awareness_required = Column(Boolean, nullable=False, server_default="f")
    rebalance_frequency = Column(String, nullable=False)
    rebalance_bands = Column(JSON, nullable=False)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    binding_version = Column(Integer, nullable=False, server_default="1")
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "mandate_id",
            "effective_from",
            "binding_version",
            name="_portfolio_mandate_binding_effective_uc",
        ),
        Index(
            "ix_portfolio_mandate_binding_effective_window",
            "portfolio_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_mandate_binding_dpm_model_book_eff",
            "model_portfolio_id",
            "booking_center_code",
            "effective_from",
            "effective_to",
            "portfolio_id",
            "mandate_id",
            postgresql_where=DPM_DISCRETIONARY_MANDATE_ACTIVE.postgresql_where(),
        ),
    )


def _enum_check_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class PortfolioPartyRoleAssignment(Base):
    __tablename__ = "portfolio_party_role_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False)
    party_id = Column(String, nullable=False)
    role_type = Column(String, nullable=False)
    role_scope = Column(String, nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    assignment_version = Column(Integer, nullable=False, server_default="1")
    source_system = Column(String, nullable=False)
    source_record_id = Column(String, nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    quality_status = Column(String, nullable=False, server_default="accepted")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "source_record_id",
            "assignment_version",
            name="uq_party_role_source_record_version",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_party_role_effective_window",
        ),
        CheckConstraint(
            "assignment_version >= 1",
            name="ck_party_role_assignment_version_positive",
        ),
        CheckConstraint(
            f"role_type IN ({_enum_check_values(PortfolioPartyRoleType)})",
            name="ck_party_role_type_governed",
        ),
        CheckConstraint(
            f"role_scope IN ({_enum_check_values(PortfolioPartyRoleScope)})",
            name="ck_party_role_scope_governed",
        ),
        CheckConstraint(
            f"quality_status IN ({_enum_check_values(PortfolioPartyRoleQualityStatus)})",
            name="ck_party_role_quality_governed",
        ),
        Index("ix_party_role_portfolio_history", "portfolio_id"),
        Index(
            "ix_party_role_portfolio_effective",
            "portfolio_id",
            "effective_from",
            "effective_to",
            "role_type",
            postgresql_where=text("quality_status = 'accepted'"),
        ),
        Index(
            "ix_party_role_party_effective",
            "party_id",
            "role_type",
            "role_scope",
            "effective_from",
            "effective_to",
            "portfolio_id",
            postgresql_where=text("quality_status = 'accepted'"),
        ),
    )


class ClientRestrictionProfile(Base):
    __tablename__ = "client_restriction_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    mandate_id = Column(String, nullable=True, index=True)
    restriction_scope = Column(String, nullable=False, index=True)
    restriction_code = Column(String, nullable=False, index=True)
    restriction_status = Column(String, nullable=False, index=True)
    restriction_source = Column(String, nullable=False)
    applies_to_buy = Column(Boolean, nullable=False, server_default="true")
    applies_to_sell = Column(Boolean, nullable=False, server_default="false")
    instrument_ids = Column(JSON, nullable=False, server_default="[]")
    asset_classes = Column(JSON, nullable=False, server_default="[]")
    issuer_ids = Column(JSON, nullable=False, server_default="[]")
    country_codes = Column(JSON, nullable=False, server_default="[]")
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    restriction_version = Column(Integer, nullable=False, server_default="1")
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "portfolio_id",
            "restriction_code",
            "effective_from",
            "restriction_version",
            name="_client_restriction_profile_effective_uc",
        ),
        Index(
            "ix_client_restriction_profile_effective_window",
            "portfolio_id",
            "client_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_client_restr_active_port_client_eff",
            "portfolio_id",
            "client_id",
            "restriction_scope",
            "restriction_code",
            effective_from.desc(),
            "effective_to",
            observed_at.desc().nulls_last(),
            restriction_version.desc(),
            updated_at.desc(),
            postgresql_where=CLIENT_RESTRICTION_ACTIVE.postgresql_where(),
        ),
    )


class SustainabilityPreferenceProfile(Base):
    __tablename__ = "sustainability_preference_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    mandate_id = Column(String, nullable=True, index=True)
    preference_framework = Column(String, nullable=False, index=True)
    preference_code = Column(String, nullable=False, index=True)
    preference_status = Column(String, nullable=False, index=True)
    preference_source = Column(String, nullable=False)
    minimum_allocation = Column(ExactNumeric(18, 10), nullable=True)
    maximum_allocation = Column(ExactNumeric(18, 10), nullable=True)
    applies_to_asset_classes = Column(JSON, nullable=False, server_default="[]")
    exclusion_codes = Column(JSON, nullable=False, server_default="[]")
    positive_tilt_codes = Column(JSON, nullable=False, server_default="[]")
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    preference_version = Column(Integer, nullable=False, server_default="1")
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_sustainability_allocations_finite",
            "minimum_allocation",
            "maximum_allocation",
        ),
        CheckConstraint(
            "minimum_allocation >= 0 AND maximum_allocation >= 0",
            name="ck_sustainability_allocations_nonnegative",
        ),
        UniqueConstraint(
            "client_id",
            "portfolio_id",
            "preference_framework",
            "preference_code",
            "effective_from",
            "preference_version",
            name="_sustainability_preference_profile_effective_uc",
        ),
        Index(
            "ix_sustainability_preference_effective_window",
            "portfolio_id",
            "client_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_sust_pref_active_port_client_eff",
            "portfolio_id",
            "client_id",
            "preference_framework",
            "preference_code",
            effective_from.desc(),
            "effective_to",
            observed_at.desc().nulls_last(),
            preference_version.desc(),
            updated_at.desc(),
            postgresql_where=SUSTAINABILITY_PREFERENCE_ACTIVE.postgresql_where(),
        ),
    )


class ClientTaxProfile(Base):
    __tablename__ = "client_tax_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    mandate_id = Column(String, nullable=True, index=True)
    tax_profile_id = Column(String, nullable=False, index=True)
    tax_residency_country = Column(String, nullable=False, index=True)
    booking_tax_jurisdiction = Column(String, nullable=False, index=True)
    tax_status = Column(String, nullable=False, index=True)
    profile_status = Column(String, nullable=False, server_default="active", index=True)
    withholding_tax_rate = Column(ExactNumeric(18, 10), nullable=True)
    capital_gains_tax_applicable = Column(Boolean, nullable=False, server_default="false")
    income_tax_applicable = Column(Boolean, nullable=False, server_default="false")
    treaty_codes = Column(JSON, nullable=False, server_default="[]")
    eligible_account_types = Column(JSON, nullable=False, server_default="[]")
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    profile_version = Column(Integer, nullable=False, server_default="1")
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_client_tax_withholding_rate_finite",
            "withholding_tax_rate",
        ),
        CheckConstraint(
            "withholding_tax_rate >= 0",
            name="ck_client_tax_withholding_rate_nonnegative",
        ),
        UniqueConstraint(
            "client_id",
            "portfolio_id",
            "tax_profile_id",
            "effective_from",
            "profile_version",
            name="_client_tax_profile_effective_uc",
        ),
        Index(
            "ix_client_tax_profile_effective_window",
            "portfolio_id",
            "client_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_client_tax_profile_active_eff",
            "portfolio_id",
            "client_id",
            "tax_profile_id",
            effective_from.desc(),
            "effective_to",
            observed_at.desc().nulls_last(),
            profile_version.desc(),
            updated_at.desc(),
            postgresql_where=CLIENT_TAX_PROFILE_ACTIVE.postgresql_where(),
        ),
    )


class ClientTaxRuleSet(Base):
    __tablename__ = "client_tax_rule_sets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    mandate_id = Column(String, nullable=True, index=True)
    rule_set_id = Column(String, nullable=False, index=True)
    tax_year = Column(Integer, nullable=False, index=True)
    jurisdiction_code = Column(String, nullable=False, index=True)
    rule_code = Column(String, nullable=False, index=True)
    rule_category = Column(String, nullable=False, index=True)
    rule_status = Column(String, nullable=False, index=True)
    rule_source = Column(String, nullable=False)
    applies_to_asset_classes = Column(JSON, nullable=False, server_default="[]")
    applies_to_security_ids = Column(JSON, nullable=False, server_default="[]")
    applies_to_income_types = Column(JSON, nullable=False, server_default="[]")
    rate = Column(ExactNumeric(18, 10), nullable=True)
    threshold_amount = Column(ExactNumeric(18, 4), nullable=True)
    threshold_currency = Column(String, nullable=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    rule_version = Column(Integer, nullable=False, server_default="1")
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_client_tax_rule_values_finite",
            "rate",
            "threshold_amount",
        ),
        CheckConstraint(
            "rate >= 0 AND threshold_amount >= 0",
            name="ck_client_tax_rule_values_nonnegative",
        ),
        UniqueConstraint(
            "client_id",
            "portfolio_id",
            "rule_set_id",
            "jurisdiction_code",
            "rule_code",
            "effective_from",
            "rule_version",
            name="_client_tax_rule_set_effective_uc",
        ),
        Index(
            "ix_client_tax_rule_set_effective_window",
            "portfolio_id",
            "client_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_client_tax_rule_active_eff",
            "portfolio_id",
            "client_id",
            "rule_set_id",
            "jurisdiction_code",
            "rule_code",
            effective_from.desc(),
            "effective_to",
            observed_at.desc().nulls_last(),
            rule_version.desc(),
            updated_at.desc(),
            postgresql_where=CLIENT_TAX_RULE_SET_ACTIVE.postgresql_where(),
        ),
    )


class ClientIncomeNeedsSchedule(Base):
    __tablename__ = "client_income_needs_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    mandate_id = Column(String, nullable=True, index=True)
    schedule_id = Column(String, nullable=False, index=True)
    need_type = Column(String, nullable=False, index=True)
    need_status = Column(String, nullable=False, server_default="active", index=True)
    amount = Column(ExactNumeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, index=True)
    frequency = Column(String, nullable=False, index=True)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=True, index=True)
    priority = Column(Integer, nullable=False, server_default="1")
    funding_policy = Column(String, nullable=True)
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_client_income_need_amount_finite",
            "amount",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_client_income_need_amount_positive",
        ),
        UniqueConstraint(
            "client_id",
            "portfolio_id",
            "schedule_id",
            "start_date",
            name="_client_income_needs_schedule_effective_uc",
        ),
        Index(
            "ix_client_income_needs_schedule_effective_window",
            "portfolio_id",
            "client_id",
            "start_date",
            "end_date",
        ),
        Index(
            "ix_client_income_needs_active_eff",
            "portfolio_id",
            "client_id",
            "schedule_id",
            start_date.desc(),
            "end_date",
            observed_at.desc().nulls_last(),
            updated_at.desc(),
            postgresql_where=CLIENT_INCOME_NEEDS_ACTIVE.postgresql_where(),
        ),
    )


class LiquidityReserveRequirement(Base):
    __tablename__ = "liquidity_reserve_requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    mandate_id = Column(String, nullable=True, index=True)
    reserve_requirement_id = Column(String, nullable=False, index=True)
    reserve_type = Column(String, nullable=False, index=True)
    reserve_status = Column(String, nullable=False, server_default="active", index=True)
    required_amount = Column(ExactNumeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, index=True)
    horizon_days = Column(Integer, nullable=False)
    priority = Column(Integer, nullable=False, server_default="1")
    policy_source = Column(String, nullable=False)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    requirement_version = Column(Integer, nullable=False, server_default="1")
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_liquidity_reserve_amount_finite",
            "required_amount",
        ),
        CheckConstraint(
            "required_amount > 0",
            name="ck_liquidity_reserve_amount_positive",
        ),
        UniqueConstraint(
            "client_id",
            "portfolio_id",
            "reserve_requirement_id",
            "effective_from",
            "requirement_version",
            name="_liquidity_reserve_requirement_effective_uc",
        ),
        Index(
            "ix_liquidity_reserve_requirement_effective_window",
            "portfolio_id",
            "client_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_liquidity_reserve_active_eff",
            "portfolio_id",
            "client_id",
            "reserve_requirement_id",
            effective_from.desc(),
            "effective_to",
            observed_at.desc().nulls_last(),
            requirement_version.desc(),
            updated_at.desc(),
            postgresql_where=LIQUIDITY_RESERVE_ACTIVE.postgresql_where(),
        ),
    )


class PlannedWithdrawalSchedule(Base):
    __tablename__ = "planned_withdrawal_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    mandate_id = Column(String, nullable=True, index=True)
    withdrawal_schedule_id = Column(String, nullable=False, index=True)
    withdrawal_type = Column(String, nullable=False, index=True)
    withdrawal_status = Column(String, nullable=False, server_default="active", index=True)
    amount = Column(ExactNumeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, index=True)
    scheduled_date = Column(Date, nullable=False, index=True)
    recurrence_frequency = Column(String, nullable=True, index=True)
    purpose_code = Column(String, nullable=True, index=True)
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_planned_withdrawal_amount_finite",
            "amount",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_planned_withdrawal_amount_positive",
        ),
        UniqueConstraint(
            "client_id",
            "portfolio_id",
            "withdrawal_schedule_id",
            "scheduled_date",
            name="_planned_withdrawal_schedule_effective_uc",
        ),
        Index(
            "ix_planned_withdrawal_schedule_window",
            "portfolio_id",
            "client_id",
            "scheduled_date",
        ),
        Index(
            "ix_planned_withdrawal_active_window",
            "portfolio_id",
            "client_id",
            "scheduled_date",
            "withdrawal_schedule_id",
            observed_at.desc().nulls_last(),
            updated_at.desc(),
            postgresql_where=PLANNED_WITHDRAWAL_ACTIVE.postgresql_where(),
        ),
    )


class InstrumentEligibilityProfile(Base):
    __tablename__ = "instrument_eligibility_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    security_id = Column(String, ForeignKey("instruments.security_id"), nullable=False, index=True)
    eligibility_status = Column(String, nullable=False, index=True)
    product_shelf_status = Column(String, nullable=False, index=True)
    buy_allowed = Column(Boolean, nullable=False, server_default="false")
    sell_allowed = Column(Boolean, nullable=False, server_default="true")
    restriction_reason_codes = Column(JSON, nullable=False, server_default="[]")
    restriction_rationale = Column(Text, nullable=True)
    settlement_days = Column(Integer, nullable=False, server_default="2")
    settlement_calendar_id = Column(String, nullable=False, server_default="GLOBAL")
    liquidity_tier = Column(String, nullable=True)
    issuer_id = Column(String, nullable=True, index=True)
    issuer_name = Column(String, nullable=True)
    ultimate_parent_issuer_id = Column(String, nullable=True, index=True)
    ultimate_parent_issuer_name = Column(String, nullable=True)
    asset_class = Column(String, nullable=True)
    country_of_risk = Column(String, nullable=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    eligibility_version = Column(Integer, nullable=False, server_default="1")
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "security_id",
            "effective_from",
            "eligibility_version",
            name="_instrument_eligibility_profile_uc",
        ),
        Index(
            "ix_instrument_eligibility_effective_window",
            "security_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_instr_elig_norm_sec_eff",
            func.trim(security_id),
            effective_from.desc(),
            "effective_to",
            observed_at.desc().nulls_last(),
            eligibility_version.desc(),
            updated_at.desc(),
        ),
    )


class ModelPortfolioDefinition(Base):
    __tablename__ = "model_portfolio_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_portfolio_id = Column(String, nullable=False, index=True)
    model_portfolio_version = Column(String, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    base_currency = Column(String(3), nullable=False)
    risk_profile = Column(String, nullable=False)
    mandate_type = Column(String, nullable=False)
    rebalance_frequency = Column(String, nullable=True)
    approval_status = Column(String, nullable=False, server_default="approved", index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "model_portfolio_id",
            "model_portfolio_version",
            "effective_from",
            name="_model_portfolio_definition_version_effective_uc",
        ),
        Index(
            "ix_model_portfolio_definition_effective_window",
            "model_portfolio_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_model_port_def_approved_eff_order",
            "model_portfolio_id",
            effective_from.desc(),
            "effective_to",
            approved_at.desc(),
            updated_at.desc(),
            postgresql_where=text("approval_status = 'approved'"),
        ),
    )


class ModelPortfolioTarget(Base):
    __tablename__ = "model_portfolio_targets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_portfolio_id = Column(String, nullable=False, index=True)
    model_portfolio_version = Column(String, nullable=False, index=True)
    instrument_id = Column(String, nullable=False, index=True)
    target_weight = Column(ExactNumeric(18, 10), nullable=False)
    min_weight = Column(ExactNumeric(18, 10), nullable=True)
    max_weight = Column(ExactNumeric(18, 10), nullable=True)
    target_status = Column(String, nullable=False, server_default="active", index=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_model_portfolio_weights_finite",
            "target_weight",
            "min_weight",
            "max_weight",
        ),
        CheckConstraint(
            "target_weight >= 0 AND min_weight >= 0 AND max_weight >= 0",
            name="ck_model_portfolio_weights_nonnegative",
        ),
        UniqueConstraint(
            "model_portfolio_id",
            "model_portfolio_version",
            "instrument_id",
            "effective_from",
            name="_model_portfolio_target_instrument_effective_uc",
        ),
        Index(
            "ix_model_portfolio_target_effective_window",
            "model_portfolio_id",
            "model_portfolio_version",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_model_port_tgt_active_eff_order",
            "model_portfolio_id",
            "model_portfolio_version",
            "instrument_id",
            effective_from.desc(),
            "effective_to",
            postgresql_where=MODEL_PORTFOLIO_TARGET_ACTIVE.postgresql_where(),
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
        Index(
            "ix_benchmark_def_active_id_eff",
            "benchmark_id",
            effective_from.desc(),
            "effective_to",
            postgresql_where=BENCHMARK_DEFINITION_ACTIVE.postgresql_where(),
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
        Index(
            "ix_index_def_active_id_eff",
            "index_id",
            effective_from.desc(),
            "effective_to",
            postgresql_where=INDEX_DEFINITION_ACTIVE.postgresql_where(),
        ),
    )


class BenchmarkCompositionSeries(Base):
    __tablename__ = "benchmark_composition_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    benchmark_id = Column(String, nullable=False, index=True)
    index_id = Column(String, nullable=False, index=True)
    composition_effective_from = Column(Date, nullable=False, index=True)
    composition_effective_to = Column(Date, nullable=True, index=True)
    composition_weight = Column(ExactNumeric(18, 10), nullable=False)
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
        _finite_numeric_check_constraint(
            "ck_benchmark_composition_weight_finite",
            "composition_weight",
        ),
        CheckConstraint(
            "composition_weight >= 0",
            name="ck_benchmark_composition_weight_nonnegative",
        ),
        UniqueConstraint(
            "benchmark_id",
            "index_id",
            "composition_effective_from",
            name="_benchmark_composition_effective_uc",
        ),
        Index(
            "ix_benchmark_composition_series_benchmark_effective_window",
            "benchmark_id",
            "composition_effective_from",
            "composition_effective_to",
        ),
        Index(
            "ix_bench_comp_benchmark_index_eff",
            "benchmark_id",
            "index_id",
            composition_effective_from.desc(),
            "composition_effective_to",
        ),
    )


class IndexPriceSeries(Base):
    __tablename__ = "index_price_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(String, nullable=False, index=True)
    index_id = Column(String, nullable=False, index=True)
    series_date = Column(Date, nullable=False, index=True)
    index_price = Column(ExactNumeric(18, 10), nullable=False)
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
        _finite_numeric_check_constraint(
            "ck_index_price_series_price_finite",
            "index_price",
        ),
        CheckConstraint(
            "index_price > 0",
            name="ck_index_price_series_price_positive",
        ),
        UniqueConstraint("series_id", "index_id", "series_date", name="_index_price_series_uc"),
        Index(
            "ix_index_price_series_index_id_series_date",
            "index_id",
            "series_date",
        ),
    )


class IndexReturnSeries(Base):
    __tablename__ = "index_return_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(String, nullable=False, index=True)
    index_id = Column(String, nullable=False, index=True)
    series_date = Column(Date, nullable=False, index=True)
    index_return = Column(ExactNumeric(18, 10), nullable=False)
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
        _finite_numeric_check_constraint(
            "ck_index_return_series_return_finite",
            "index_return",
        ),
        UniqueConstraint("series_id", "index_id", "series_date", name="_index_return_series_uc"),
        Index(
            "ix_index_return_series_index_id_series_date",
            "index_id",
            "series_date",
        ),
    )


class BenchmarkReturnSeries(Base):
    __tablename__ = "benchmark_return_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(String, nullable=False, index=True)
    benchmark_id = Column(String, nullable=False, index=True)
    series_date = Column(Date, nullable=False, index=True)
    benchmark_return = Column(ExactNumeric(18, 10), nullable=False)
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
        _finite_numeric_check_constraint(
            "ck_benchmark_return_series_return_finite",
            "benchmark_return",
        ),
        UniqueConstraint(
            "series_id",
            "benchmark_id",
            "series_date",
            name="_benchmark_return_series_uc",
        ),
        Index(
            "ix_benchmark_return_series_benchmark_id_series_date",
            "benchmark_id",
            "series_date",
        ),
    )


class RiskFreeSeries(Base):
    __tablename__ = "risk_free_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(String, nullable=False, index=True)
    risk_free_curve_id = Column(String, nullable=False, index=True)
    series_date = Column(Date, nullable=False, index=True)
    value = Column(ExactNumeric(18, 10), nullable=False)
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
        _finite_numeric_check_constraint(
            "ck_risk_free_series_value_finite",
            "value",
        ),
        UniqueConstraint(
            "series_id",
            "risk_free_curve_id",
            "series_date",
            name="_risk_free_series_uc",
        ),
        Index(
            "ix_risk_free_series_currency_series_date",
            "series_currency",
            "series_date",
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


class CashAccountMaster(Base):
    __tablename__ = "cash_account_masters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cash_account_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), nullable=False, index=True)
    security_id = Column(String, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    account_currency = Column(String(3), nullable=False, index=True)
    account_role = Column(String, nullable=True, index=True)
    lifecycle_status = Column(String, nullable=False, server_default="ACTIVE", index=True)
    opened_on = Column(Date, nullable=True, index=True)
    closed_on = Column(Date, nullable=True, index=True)
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("cash_account_id", name="_cash_account_master_id_uc"),
        Index(
            "ix_cash_account_master_portfolio_effective_window",
            "portfolio_id",
            "opened_on",
            "closed_on",
        ),
        Index(
            "ix_cash_account_port_currency_id",
            "portfolio_id",
            "account_currency",
            "cash_account_id",
        ),
    )


class InstrumentLookthroughComponent(Base):
    __tablename__ = "instrument_lookthrough_components"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_security_id = Column(String, nullable=False, index=True)
    component_security_id = Column(String, nullable=False, index=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    component_weight = Column(ExactNumeric(18, 10), nullable=False)
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_instrument_lookthrough_weight_finite",
            "component_weight",
        ),
        CheckConstraint(
            "component_weight >= 0",
            name="ck_instrument_lookthrough_weight_nonnegative",
        ),
        UniqueConstraint(
            "parent_security_id",
            "component_security_id",
            "effective_from",
            name="_instrument_lookthrough_component_effective_uc",
        ),
        Index(
            "ix_instrument_lookthrough_parent_effective_window",
            "parent_security_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_lookthrough_norm_parent_eff_comp",
            func.trim(parent_security_id),
            effective_from.desc(),
            "effective_to",
            func.trim(component_security_id),
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
    quantity = Column(ExactNumeric(18, 10), nullable=False)
    price = Column(ExactNumeric(18, 10), nullable=False)
    gross_transaction_amount = Column(ExactNumeric(18, 10), nullable=False)
    trade_currency = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    settlement_date = Column(DateTime(timezone=True), nullable=True)
    trade_fee = Column(ExactNumeric(18, 10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    gross_cost = Column(ExactNumeric(18, 10), nullable=True)
    net_cost = Column(ExactNumeric(18, 10), nullable=True)
    realized_gain_loss = Column(ExactNumeric(18, 10), nullable=True)
    transaction_fx_rate = Column(ExactNumeric(18, 10), nullable=True)
    net_cost_local = Column(ExactNumeric(18, 10), nullable=True)
    realized_gain_loss_local = Column(ExactNumeric(18, 10), nullable=True)
    economic_event_id = Column(String, nullable=True, index=True)
    linked_transaction_group_id = Column(String, nullable=True, index=True)
    calculation_policy_id = Column(String, nullable=True)
    calculation_policy_version = Column(String, nullable=True)
    calculation_lineage = Column(JSON(none_as_null=True), nullable=True)
    source_system = Column(String, nullable=True)
    cash_entry_mode = Column(String, nullable=True)
    external_cash_transaction_id = Column(String, nullable=True, index=True)
    settlement_cash_account_id = Column(String, nullable=True, index=True)
    settlement_cash_instrument_id = Column(String, nullable=True)
    movement_direction = Column(String, nullable=True)
    originating_transaction_id = Column(String, nullable=True, index=True)
    originating_transaction_type = Column(String, nullable=True)
    adjustment_reason = Column(String, nullable=True)
    link_type = Column(String, nullable=True)
    reconciliation_key = Column(String, nullable=True, index=True)
    interest_direction = Column(String, nullable=True, index=True)
    withholding_tax_amount = Column(ExactNumeric(18, 10), nullable=True)
    other_interest_deductions_amount = Column(ExactNumeric(18, 10), nullable=True)
    net_interest_amount = Column(ExactNumeric(18, 10), nullable=True)
    component_type = Column(String, nullable=True, index=True)
    component_id = Column(String, nullable=True, index=True)
    linked_component_ids = Column(JSON, nullable=True)
    fx_cash_leg_role = Column(String, nullable=True, index=True)
    linked_fx_cash_leg_id = Column(String, nullable=True, index=True)
    settlement_status = Column(String, nullable=True, index=True)
    pair_base_currency = Column(String(3), nullable=True)
    pair_quote_currency = Column(String(3), nullable=True)
    fx_rate_quote_convention = Column(String, nullable=True)
    buy_currency = Column(String(3), nullable=True)
    sell_currency = Column(String(3), nullable=True)
    buy_amount = Column(ExactNumeric(18, 10), nullable=True)
    sell_amount = Column(ExactNumeric(18, 10), nullable=True)
    contract_rate = Column(ExactNumeric(18, 10), nullable=True)
    fx_contract_id = Column(String, nullable=True, index=True)
    fx_contract_open_transaction_id = Column(String, nullable=True, index=True)
    fx_contract_close_transaction_id = Column(String, nullable=True, index=True)
    settlement_of_fx_contract_id = Column(String, nullable=True, index=True)
    swap_event_id = Column(String, nullable=True, index=True)
    near_leg_group_id = Column(String, nullable=True, index=True)
    far_leg_group_id = Column(String, nullable=True, index=True)
    spot_exposure_model = Column(String, nullable=True)
    fx_realized_pnl_mode = Column(String, nullable=True)
    allocated_cost_basis_local = Column(ExactNumeric(18, 10), nullable=True)
    allocated_cost_basis_base = Column(ExactNumeric(18, 10), nullable=True)
    realized_capital_pnl_local = Column(ExactNumeric(18, 10), nullable=True)
    realized_fx_pnl_local = Column(ExactNumeric(18, 10), nullable=True)
    realized_total_pnl_local = Column(ExactNumeric(18, 10), nullable=True)
    realized_capital_pnl_base = Column(ExactNumeric(18, 10), nullable=True)
    realized_fx_pnl_base = Column(ExactNumeric(18, 10), nullable=True)
    realized_total_pnl_base = Column(ExactNumeric(18, 10), nullable=True)
    parent_transaction_reference = Column(String, nullable=True, index=True)
    linked_parent_event_id = Column(String, nullable=True, index=True)
    parent_event_reference = Column(String, nullable=True, index=True)
    child_role = Column(String, nullable=True)
    child_sequence_hint = Column(Integer, nullable=True)
    dependency_reference_ids = Column(JSON, nullable=True)
    source_instrument_id = Column(String, nullable=True, index=True)
    target_instrument_id = Column(String, nullable=True, index=True)
    source_transaction_reference = Column(String, nullable=True, index=True)
    target_transaction_reference = Column(String, nullable=True, index=True)
    external_destination_reference = Column(String, nullable=True)
    linked_cash_transaction_id = Column(String, nullable=True, index=True)
    redemption_price_type = Column(String, nullable=True)
    old_factor = Column(ExactNumeric(18, 10), nullable=True)
    new_factor = Column(ExactNumeric(18, 10), nullable=True)
    principal_proceeds_local = Column(ExactNumeric(18, 10), nullable=True)
    accrued_interest_proceeds_local = Column(ExactNumeric(18, 10), nullable=True)
    embedded_fee_amount_local = Column(ExactNumeric(18, 10), nullable=True)
    embedded_tax_amount_local = Column(ExactNumeric(18, 10), nullable=True)
    has_synthetic_flow = Column(Boolean, nullable=True)
    synthetic_flow_effective_date = Column(Date, nullable=True, index=True)
    synthetic_flow_amount_local = Column(ExactNumeric(18, 10), nullable=True)
    synthetic_flow_currency = Column(String(3), nullable=True)
    synthetic_flow_amount_base = Column(ExactNumeric(18, 10), nullable=True)
    synthetic_flow_fx_rate_to_base = Column(ExactNumeric(18, 10), nullable=True)
    synthetic_flow_price_used = Column(ExactNumeric(18, 10), nullable=True)
    synthetic_flow_quantity_used = Column(ExactNumeric(18, 10), nullable=True)
    synthetic_flow_valuation_method = Column(String, nullable=True)
    synthetic_flow_classification = Column(String, nullable=True, index=True)
    synthetic_flow_price_source = Column(String, nullable=True)
    synthetic_flow_fx_source = Column(String, nullable=True)
    synthetic_flow_source = Column(String, nullable=True)

    costs = relationship(
        "TransactionCost", back_populates="transaction", cascade="all, delete-orphan"
    )
    cashflow = relationship(
        "Cashflow", uselist=False, back_populates="transaction", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "CAST(quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_transactions_quantity_finite",
        ),
        CheckConstraint(
            "quantity >= 0",
            name="ck_transactions_quantity_nonnegative",
        ),
        _finite_numeric_check_constraint(
            "ck_transactions_trade_values_finite",
            "price",
            "gross_transaction_amount",
            "trade_fee",
            "gross_cost",
            "net_cost",
            "realized_gain_loss",
            "transaction_fx_rate",
            "net_cost_local",
            "realized_gain_loss_local",
        ),
        CheckConstraint(
            "price >= 0 AND gross_transaction_amount >= 0 AND trade_fee >= 0 "
            "AND transaction_fx_rate > 0",
            name="ck_transactions_trade_values_sign",
        ),
        _finite_numeric_check_constraint(
            "ck_transactions_income_values_finite",
            "withholding_tax_amount",
            "other_interest_deductions_amount",
            "net_interest_amount",
        ),
        CheckConstraint(
            "withholding_tax_amount >= 0 AND other_interest_deductions_amount >= 0 "
            "AND net_interest_amount >= 0",
            name="ck_transactions_income_values_nonnegative",
        ),
        _finite_numeric_check_constraint(
            "ck_transactions_fx_terms_finite",
            "buy_amount",
            "sell_amount",
            "contract_rate",
        ),
        CheckConstraint(
            "buy_amount > 0 AND sell_amount > 0 AND contract_rate > 0",
            name="ck_transactions_fx_terms_positive",
        ),
        _finite_numeric_check_constraint(
            "ck_transactions_realized_values_finite",
            "allocated_cost_basis_local",
            "allocated_cost_basis_base",
            "realized_capital_pnl_local",
            "realized_fx_pnl_local",
            "realized_total_pnl_local",
            "realized_capital_pnl_base",
            "realized_fx_pnl_base",
            "realized_total_pnl_base",
        ),
        CheckConstraint(
            "allocated_cost_basis_local >= 0 AND allocated_cost_basis_base >= 0",
            name="ck_transactions_allocated_basis_nonnegative",
        ),
        _finite_numeric_check_constraint(
            "ck_transactions_redemption_values_finite",
            "old_factor",
            "new_factor",
            "principal_proceeds_local",
            "accrued_interest_proceeds_local",
            "embedded_fee_amount_local",
            "embedded_tax_amount_local",
        ),
        CheckConstraint(
            "(old_factor IS NULL AND new_factor IS NULL) OR "
            "(old_factor IS NOT NULL AND new_factor IS NOT NULL "
            "AND old_factor > 0 AND new_factor >= 0 AND new_factor < old_factor)",
            name="ck_transactions_redemption_factor_transition",
        ),
        CheckConstraint(
            "principal_proceeds_local >= 0 AND accrued_interest_proceeds_local >= 0 "
            "AND embedded_fee_amount_local >= 0 AND embedded_tax_amount_local >= 0",
            name="ck_transactions_redemption_amounts_nonnegative",
        ),
        _finite_numeric_check_constraint(
            "ck_transactions_synthetic_flow_values_finite",
            "synthetic_flow_amount_local",
            "synthetic_flow_amount_base",
            "synthetic_flow_fx_rate_to_base",
            "synthetic_flow_price_used",
            "synthetic_flow_quantity_used",
        ),
        CheckConstraint(
            "synthetic_flow_fx_rate_to_base > 0 AND synthetic_flow_price_used >= 0 "
            "AND synthetic_flow_quantity_used >= 0",
            name="ck_transactions_synthetic_flow_values_sign",
        ),
        Index("ix_transactions_portfolio_security", "portfolio_id", "security_id"),
        Index(
            "ix_transactions_portfolio_instrument_date",
            "portfolio_id",
            "instrument_id",
            "transaction_date",
        ),
        Index(
            "ix_transactions_portfolio_settlement_cash_instrument_date",
            "portfolio_id",
            "settlement_cash_instrument_id",
            "transaction_date",
        ),
        Index(
            "ix_transactions_portfolio_type_date",
            "portfolio_id",
            "transaction_type",
            "transaction_date",
        ),
        Index(
            "ix_txn_norm_port_sec_date_id",
            func.trim(portfolio_id),
            func.trim(security_id),
            transaction_date,
            transaction_id,
        ),
        Index(
            "ix_txn_norm_port_sec_date_qty_id",
            func.trim(portfolio_id),
            func.trim(security_id),
            transaction_date,
            quantity.desc(),
            transaction_id,
        ),
        Index(
            "ix_txn_port_date_id",
            "portfolio_id",
            transaction_date.desc(),
            id.desc(),
        ),
        Index(
            "ix_txn_port_norm_sec_date_id",
            "portfolio_id",
            func.trim(security_id),
            transaction_date.desc(),
            id.desc(),
        ),
        Index(
            "ix_txn_port_norm_sec_type_date_id",
            "portfolio_id",
            func.trim(security_id),
            "transaction_type",
            transaction_date.desc(),
            id.desc(),
        ),
        Index(
            "ix_txn_port_norm_cash_instr_date_id",
            "portfolio_id",
            func.trim(settlement_cash_instrument_id),
            transaction_date.desc(),
            id.desc(),
        ),
        Index(
            "ix_txn_port_linked_group_date_id",
            "portfolio_id",
            "linked_transaction_group_id",
            transaction_date.desc(),
            id.desc(),
        ),
        Index(
            "ix_txn_port_settlement_date_id",
            "portfolio_id",
            settlement_date,
            id,
        ),
        Index(
            "ix_txn_projected_cash_external_port_settle_txn_date_id",
            "portfolio_id",
            "settlement_date",
            "transaction_date",
            "id",
            postgresql_where=text(
                "transaction_type IN ('DEPOSIT', 'WITHDRAWAL') AND settlement_date IS NOT NULL"
            ),
        ),
        Index(
            "ix_txn_realized_tax_evidence_port_currency_date_txn",
            "portfolio_id",
            "currency",
            "transaction_date",
            "transaction_id",
            postgresql_where=text(
                "withholding_tax_amount IS NOT NULL OR other_interest_deductions_amount IS NOT NULL"
            ),
        ),
    )


class CorporateActionEventRecord(Base):
    """Mutable pointer and CAS state for one book-scoped corporate-action event."""

    __tablename__ = "corporate_action_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, nullable=False)
    legal_book_id = Column(String, nullable=False)
    portfolio_id = Column(String, nullable=False)
    corporate_action_event_id = Column(String, nullable=False)
    linked_transaction_group_id = Column(String, nullable=False)
    parent_event_reference = Column(String, nullable=False)
    current_manifest_version = Column(Integer, nullable=True)
    last_observation_sequence = Column(Integer, nullable=False, server_default="0")
    state_version = Column(Integer, nullable=False, server_default="0")
    readiness_status = Column(String, nullable=False, server_default="AWAITING_MANIFEST")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "legal_book_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.legal_book_id", "portfolios.portfolio_id"],
            name="fk_ca_event_book_scope",
        ),
        ForeignKeyConstraint(
            ["id", "current_manifest_version"],
            [
                "corporate_action_manifest_versions.event_id",
                "corporate_action_manifest_versions.manifest_version",
            ],
            name="fk_ca_event_current_manifest",
            use_alter=True,
        ),
        UniqueConstraint(
            "portfolio_id",
            "corporate_action_event_id",
            name="uq_ca_event_portfolio_identity",
        ),
        UniqueConstraint(
            "portfolio_id",
            "linked_transaction_group_id",
            "parent_event_reference",
            name="uq_ca_event_parent_group",
        ),
        CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' "
            "AND legal_book_id = btrim(legal_book_id) AND legal_book_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND corporate_action_event_id = btrim(corporate_action_event_id) "
            "AND corporate_action_event_id <> '' "
            "AND linked_transaction_group_id = btrim(linked_transaction_group_id) "
            "AND linked_transaction_group_id <> '' "
            "AND parent_event_reference = btrim(parent_event_reference) "
            "AND parent_event_reference <> ''",
            name="ck_ca_event_identity_normalized",
        ),
        CheckConstraint(
            "current_manifest_version IS NULL OR current_manifest_version >= 1",
            name="ck_ca_event_manifest_version",
        ),
        CheckConstraint(
            "last_observation_sequence >= 0 AND state_version >= 0",
            name="ck_ca_event_counters_nonnegative",
        ),
        CheckConstraint(
            "readiness_status IN ('AWAITING_MANIFEST', 'AWAITING_COMPLETION', "
            "'AWAITING_CHILDREN', 'INVALID', 'READY')",
            name="ck_ca_event_readiness_status",
        ),
        CheckConstraint(
            "(current_manifest_version IS NULL AND readiness_status = 'AWAITING_MANIFEST') "
            "OR (current_manifest_version IS NOT NULL "
            "AND readiness_status <> 'AWAITING_MANIFEST')",
            name="ck_ca_event_manifest_status_shape",
        ),
        Index(
            "ix_ca_event_portfolio_status_updated",
            "portfolio_id",
            "readiness_status",
            updated_at.desc(),
        ),
        Index(
            "ix_ca_event_book_scope_updated",
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            updated_at.desc(),
            id.desc(),
        ),
    )


class CorporateActionManifestVersionRecord(Base):
    """Immutable source-owned parent-manifest version and content identity."""

    __tablename__ = "corporate_action_manifest_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(
        Integer,
        ForeignKey("corporate_action_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manifest_version = Column(Integer, nullable=False)
    corporate_action_type = Column(String, nullable=False)
    completion_declared = Column(Boolean, nullable=False)
    source_system = Column(String, nullable=False)
    source_record_id = Column(String, nullable=False)
    source_revision = Column(String, nullable=False)
    source_content_hash = Column(String(64), nullable=False)
    source_observed_at = Column(DateTime(timezone=True), nullable=False)
    manifest_content_hash = Column(String(64), nullable=False)
    previous_manifest_id = Column(Integer, nullable=True)
    previous_manifest_content_hash = Column(String(64), nullable=True)
    expected_node_count = Column(Integer, nullable=False)
    expected_edge_count = Column(Integer, nullable=False)
    opened_observation_sequence = Column(Integer, nullable=False)
    manifest_payload = Column(JSONB(none_as_null=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "id",
            name="uq_ca_manifest_event_record",
        ),
        UniqueConstraint(
            "event_id",
            "manifest_version",
            name="uq_ca_manifest_event_version",
        ),
        UniqueConstraint(
            "event_id",
            "source_system",
            "source_record_id",
            "source_revision",
            name="uq_ca_manifest_source_revision",
        ),
        UniqueConstraint(
            "event_id",
            "manifest_content_hash",
            name="uq_ca_manifest_event_content",
        ),
        ForeignKeyConstraint(
            ["event_id", "previous_manifest_id"],
            [
                "corporate_action_manifest_versions.event_id",
                "corporate_action_manifest_versions.id",
            ],
            name="fk_ca_manifest_predecessor",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "manifest_version >= 1 AND expected_node_count >= 0 "
            "AND expected_edge_count >= 0 AND opened_observation_sequence >= 0",
            name="ck_ca_manifest_counts",
        ),
        CheckConstraint(
            "corporate_action_type = btrim(corporate_action_type) "
            "AND corporate_action_type <> '' "
            "AND source_system = btrim(source_system) AND source_system <> '' "
            "AND source_record_id = btrim(source_record_id) AND source_record_id <> '' "
            "AND source_revision = btrim(source_revision) AND source_revision <> ''",
            name="ck_ca_manifest_identity_normalized",
        ),
        CheckConstraint(
            "source_content_hash ~ '^[0-9a-f]{64}$' "
            "AND manifest_content_hash ~ '^[0-9a-f]{64}$' "
            "AND (previous_manifest_content_hash IS NULL "
            "OR previous_manifest_content_hash ~ '^[0-9a-f]{64}$')",
            name="ck_ca_manifest_hashes",
        ),
        CheckConstraint(
            "(manifest_version = 1 AND previous_manifest_id IS NULL "
            "AND previous_manifest_content_hash IS NULL) "
            "OR (manifest_version > 1 AND previous_manifest_id IS NOT NULL "
            "AND previous_manifest_content_hash IS NOT NULL)",
            name="ck_ca_manifest_chain_shape",
        ),
        CheckConstraint(
            "source_observed_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_manifest_observed_at_finite",
        ),
        CheckConstraint(
            "jsonb_typeof(manifest_payload) = 'object'",
            name="ck_ca_manifest_payload_object",
        ),
        Index(
            "ix_ca_manifest_source_history",
            "source_system",
            "source_record_id",
            "source_revision",
        ),
    )


class CorporateActionManifestNodeRecord(Base):
    """Immutable expected child node for one parent-manifest version."""

    __tablename__ = "corporate_action_manifest_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manifest_id = Column(
        Integer,
        ForeignKey("corporate_action_manifest_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    transaction_id = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)
    child_role = Column(String, nullable=False)
    child_sequence_hint = Column(Integer, nullable=True)
    instrument_id = Column(String, nullable=True)
    source_instrument_id = Column(String, nullable=True)
    target_instrument_id = Column(String, nullable=True)
    child_content_hash = Column(String(64), nullable=False)
    resolved_execution_ordinal = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "manifest_id",
            "transaction_id",
            name="uq_ca_manifest_node_identity",
        ),
        CheckConstraint(
            "transaction_id = btrim(transaction_id) AND transaction_id <> '' "
            "AND transaction_type = btrim(transaction_type) AND transaction_type <> '' "
            "AND child_role = btrim(child_role) AND child_role <> ''",
            name="ck_ca_manifest_node_normalized",
        ),
        CheckConstraint(
            "(instrument_id IS NULL OR "
            "(instrument_id = btrim(instrument_id) AND instrument_id <> '')) "
            "AND (source_instrument_id IS NULL OR "
            "(source_instrument_id = btrim(source_instrument_id) "
            "AND source_instrument_id <> '')) "
            "AND (target_instrument_id IS NULL OR "
            "(target_instrument_id = btrim(target_instrument_id) "
            "AND target_instrument_id <> ''))",
            name="ck_ca_manifest_node_instruments",
        ),
        CheckConstraint(
            "child_sequence_hint IS NULL OR child_sequence_hint >= 0",
            name="ck_ca_manifest_node_sequence",
        ),
        CheckConstraint(
            "resolved_execution_ordinal IS NULL OR resolved_execution_ordinal >= 0",
            name="ck_ca_manifest_node_ordinal",
        ),
        CheckConstraint(
            "child_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_ca_manifest_node_hash",
        ),
        Index(
            "ix_ca_manifest_node_order",
            "manifest_id",
            "resolved_execution_ordinal",
            "transaction_id",
        ),
        Index("ix_ca_manifest_node_transaction", "transaction_id"),
        Index(
            "uq_ca_manifest_node_resolved_ordinal",
            "manifest_id",
            "resolved_execution_ordinal",
            unique=True,
            postgresql_where=text("resolved_execution_ordinal IS NOT NULL"),
        ),
    )


class CorporateActionManifestEdgeRecord(Base):
    """Immutable predecessor edge within one parent-manifest version."""

    __tablename__ = "corporate_action_manifest_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manifest_id = Column(
        Integer,
        ForeignKey("corporate_action_manifest_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    predecessor_transaction_id = Column(String, nullable=False)
    successor_transaction_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["manifest_id", "predecessor_transaction_id"],
            [
                "corporate_action_manifest_nodes.manifest_id",
                "corporate_action_manifest_nodes.transaction_id",
            ],
            name="fk_ca_edge_predecessor_node",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["manifest_id", "successor_transaction_id"],
            [
                "corporate_action_manifest_nodes.manifest_id",
                "corporate_action_manifest_nodes.transaction_id",
            ],
            name="fk_ca_edge_successor_node",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "manifest_id",
            "predecessor_transaction_id",
            "successor_transaction_id",
            name="uq_ca_manifest_edge",
        ),
        CheckConstraint(
            "predecessor_transaction_id <> successor_transaction_id",
            name="ck_ca_manifest_edge_not_self",
        ),
        Index(
            "ix_ca_manifest_edge_successor",
            "manifest_id",
            "successor_transaction_id",
        ),
    )


class CorporateActionChildObservationRecord(Base):
    """Append-only child arrival evidence used to reconstruct readiness after restart."""

    __tablename__ = "corporate_action_child_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(
        Integer,
        ForeignKey("corporate_action_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    observation_sequence = Column(Integer, nullable=False)
    transaction_id = Column(
        String,
        ForeignKey("transactions.transaction_id", ondelete="RESTRICT"),
        nullable=False,
    )
    transaction_epoch = Column(Integer, nullable=False)
    delivery_event_id = Column(String, nullable=False)
    correlation_id = Column(String, nullable=True)
    observed_content_hash = Column(String(64), nullable=False)
    transaction_payload_fingerprint = Column(String(71), nullable=False)
    observed_payload = Column(JSONB(none_as_null=True), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "observation_sequence",
            name="uq_ca_observation_sequence",
        ),
        UniqueConstraint(
            "event_id",
            "delivery_event_id",
            name="uq_ca_observation_delivery",
        ),
        CheckConstraint(
            "observation_sequence >= 1 AND transaction_epoch >= 0",
            name="ck_ca_observation_counters",
        ),
        CheckConstraint(
            "delivery_event_id = btrim(delivery_event_id) AND delivery_event_id <> '' "
            "AND transaction_id = btrim(transaction_id) AND transaction_id <> ''",
            name="ck_ca_observation_identity_normalized",
        ),
        CheckConstraint(
            "observed_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_ca_observation_hash",
        ),
        CheckConstraint(
            "transaction_payload_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_ca_observation_transaction_fingerprint",
        ),
        CheckConstraint(
            "observed_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_observation_observed_at_finite",
        ),
        CheckConstraint(
            "jsonb_typeof(observed_payload) = 'object'",
            name="ck_ca_observation_payload_object",
        ),
        Index(
            "ix_ca_observation_event_transaction",
            "event_id",
            "transaction_id",
            transaction_epoch.desc(),
            observation_sequence.desc(),
        ),
        Index("ix_ca_observation_transaction", "transaction_id"),
    )


class CorporateActionReadinessEvaluationRecord(Base):
    """Append-only deterministic evaluation and execution-plan evidence."""

    __tablename__ = "corporate_action_readiness_evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(
        Integer,
        ForeignKey("corporate_action_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state_version = Column(Integer, nullable=False)
    manifest_id = Column(
        Integer,
        nullable=True,
    )
    through_observation_sequence = Column(Integer, nullable=False)
    readiness_status = Column(String, nullable=False)
    manifest_content_hash = Column(String(64), nullable=True)
    execution_plan_content_hash = Column(String(64), nullable=True)
    findings = Column(JSONB(none_as_null=True), nullable=False)
    ordered_transaction_ids = Column(JSONB(none_as_null=True), nullable=False)
    correlation_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "manifest_id"],
            [
                "corporate_action_manifest_versions.event_id",
                "corporate_action_manifest_versions.id",
            ],
            name="fk_ca_readiness_event_manifest",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "event_id",
            "state_version",
            name="uq_ca_readiness_state_version",
        ),
        CheckConstraint(
            "state_version >= 1 AND through_observation_sequence >= 0",
            name="ck_ca_readiness_counters",
        ),
        CheckConstraint(
            "readiness_status IN ('AWAITING_MANIFEST', 'AWAITING_COMPLETION', "
            "'AWAITING_CHILDREN', 'INVALID', 'READY')",
            name="ck_ca_readiness_status",
        ),
        CheckConstraint(
            "(manifest_content_hash IS NULL OR manifest_content_hash ~ '^[0-9a-f]{64}$') "
            "AND (execution_plan_content_hash IS NULL "
            "OR execution_plan_content_hash ~ '^[0-9a-f]{64}$')",
            name="ck_ca_readiness_hashes",
        ),
        CheckConstraint(
            "jsonb_typeof(findings) = 'array' AND jsonb_typeof(ordered_transaction_ids) = 'array'",
            name="ck_ca_readiness_evidence_arrays",
        ),
        CheckConstraint(
            "(manifest_id IS NULL AND readiness_status = 'AWAITING_MANIFEST' "
            "AND manifest_content_hash IS NULL) "
            "OR (manifest_id IS NOT NULL AND readiness_status <> 'AWAITING_MANIFEST' "
            "AND manifest_content_hash IS NOT NULL)",
            name="ck_ca_readiness_manifest_shape",
        ),
        CheckConstraint(
            "(readiness_status = 'READY' AND execution_plan_content_hash IS NOT NULL "
            "AND jsonb_array_length(findings) = 0 "
            "AND jsonb_array_length(ordered_transaction_ids) > 0) "
            "OR (readiness_status <> 'READY' AND execution_plan_content_hash IS NULL "
            "AND jsonb_array_length(ordered_transaction_ids) = 0)",
            name="ck_ca_readiness_ready_shape",
        ),
        Index(
            "ix_ca_readiness_status_created",
            "readiness_status",
            created_at.desc(),
        ),
    )


class CorporateActionExecutionReleaseRecord(Base):
    """Durable, lease-fenced release of one immutable READY evaluation."""

    __tablename__ = "corporate_action_execution_releases"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    readiness_evaluation_id = Column(
        Integer,
        ForeignKey("corporate_action_readiness_evaluations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    structural_plan_content_hash = Column(String(64), nullable=False)
    release_authority_hash = Column(String(64), nullable=False)
    status = Column(String, nullable=False, server_default="PENDING")
    next_execution_ordinal = Column(Integer, nullable=False, server_default="0")
    member_count = Column(Integer, nullable=False)
    attempt_count = Column(Integer, nullable=False, server_default="0")
    fence_token = Column(BigInteger, nullable=False, server_default="0")
    lease_owner = Column(String(128), nullable=True)
    lease_token = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    terminal_reason = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "readiness_evaluation_id",
            name="uq_ca_execution_release_readiness",
        ),
        UniqueConstraint(
            "release_authority_hash",
            name="uq_ca_execution_release_authority",
        ),
        CheckConstraint(
            "structural_plan_content_hash ~ '^[0-9a-f]{64}$' "
            "AND release_authority_hash ~ '^[0-9a-f]{64}$'",
            name="ck_ca_execution_release_hashes",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETE', 'FAILED', 'SUPERSEDED')",
            name="ck_ca_execution_release_status",
        ),
        CheckConstraint(
            "member_count > 0 AND next_execution_ordinal >= 0 "
            "AND next_execution_ordinal <= member_count "
            "AND attempt_count >= 0 AND fence_token >= 0",
            name="ck_ca_execution_release_counters",
        ),
        CheckConstraint(
            "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="ck_ca_execution_release_lease_complete",
        ),
        CheckConstraint(
            "lease_owner IS NULL OR (lease_owner = btrim(lease_owner) AND lease_owner <> '')",
            name="ck_ca_execution_release_owner_normalized",
        ),
        CheckConstraint(
            "lease_token IS NULL OR lease_token ~ '^[0-9a-f]{64}$'",
            name="ck_ca_execution_release_lease_token",
        ),
        CheckConstraint(
            "lease_expires_at IS NULL OR "
            "lease_expires_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_execution_release_lease_expiry_finite",
        ),
        CheckConstraint(
            "(status = 'PROCESSING' AND lease_owner IS NOT NULL "
            "AND completed_at IS NULL AND terminal_reason IS NULL) OR "
            "(status = 'PENDING' AND lease_owner IS NULL "
            "AND completed_at IS NULL AND terminal_reason IS NULL) OR "
            "(status = 'COMPLETE' AND lease_owner IS NULL "
            "AND next_execution_ordinal = member_count "
            "AND completed_at IS NOT NULL AND terminal_reason IS NULL) OR "
            "(status = 'FAILED' AND lease_owner IS NULL "
            "AND completed_at IS NULL AND terminal_reason IS NOT NULL) OR "
            "(status = 'SUPERSEDED' AND lease_owner IS NULL "
            "AND next_execution_ordinal = 0 "
            "AND completed_at IS NULL AND terminal_reason IS NOT NULL)",
            name="ck_ca_execution_release_state_shape",
        ),
        CheckConstraint(
            "completed_at IS NULL OR "
            "completed_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_execution_release_completed_finite",
        ),
        Index(
            "ix_ca_execution_release_claim",
            "status",
            "lease_expires_at",
            "id",
        ),
    )


class CorporateActionExecutionMemberRecord(Base):
    """Ordered member progress for a corporate-action execution release."""

    __tablename__ = "corporate_action_execution_members"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    release_id = Column(
        BigInteger,
        ForeignKey("corporate_action_execution_releases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    execution_ordinal = Column(Integer, nullable=False)
    transaction_id = Column(
        String,
        ForeignKey("transactions.transaction_id", ondelete="RESTRICT"),
        nullable=False,
    )
    observation_id = Column(
        Integer,
        ForeignKey("corporate_action_child_observations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    transaction_epoch = Column(Integer, nullable=False)
    observed_child_content_hash = Column(String(64), nullable=False)
    transaction_payload_fingerprint = Column(String(71), nullable=False)
    status = Column(String, nullable=False, server_default="PENDING")
    completed_fence_token = Column(BigInteger, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "execution_ordinal",
            name="uq_ca_execution_member_ordinal",
        ),
        UniqueConstraint(
            "release_id",
            "transaction_id",
            name="uq_ca_execution_member_transaction",
        ),
        UniqueConstraint(
            "release_id",
            "observation_id",
            name="uq_ca_execution_member_observation",
        ),
        CheckConstraint(
            "execution_ordinal >= 0",
            name="ck_ca_execution_member_ordinal",
        ),
        CheckConstraint(
            "transaction_id = btrim(transaction_id) AND transaction_id <> ''",
            name="ck_ca_execution_member_transaction_normalized",
        ),
        CheckConstraint(
            "transaction_epoch >= 0",
            name="ck_ca_execution_member_epoch",
        ),
        CheckConstraint(
            "observed_child_content_hash ~ '^[0-9a-f]{64}$' "
            "AND transaction_payload_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_ca_execution_member_hashes",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'COMPLETE')",
            name="ck_ca_execution_member_status",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND completed_fence_token IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'COMPLETE' AND completed_fence_token > 0 "
            "AND completed_at IS NOT NULL)",
            name="ck_ca_execution_member_state_shape",
        ),
        CheckConstraint(
            "completed_at IS NULL OR "
            "completed_at NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ca_execution_member_completed_finite",
        ),
        Index(
            "ix_ca_execution_member_pending",
            "release_id",
            "status",
            "execution_ordinal",
        ),
        Index("ix_ca_execution_member_transaction", "transaction_id"),
    )


class TransactionCost(Base):
    __tablename__ = "transaction_costs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, ForeignKey("transactions.transaction_id"), nullable=False)
    fee_type = Column(String, nullable=False)
    amount = Column(ExactNumeric(18, 10), nullable=False)
    currency = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    transaction = relationship("Transaction", back_populates="costs")

    __table_args__ = (
        CheckConstraint(
            "CAST(amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_transaction_costs_amount_finite",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_transaction_costs_amount_positive",
        ),
        Index("ix_transaction_costs_transaction_id", "transaction_id"),
        Index(
            "ix_txn_costs_positive_txn_id",
            "transaction_id",
            postgresql_where=text("amount > 0"),
        ),
        Index(
            "uq_transaction_costs_component_identity",
            "transaction_id",
            func.lower(func.trim(fee_type)),
            func.upper(func.trim(currency)),
            unique=True,
        ),
    )


class Cashflow(Base):
    __tablename__ = "cashflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, ForeignKey("transactions.transaction_id"), nullable=False)
    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), index=True, nullable=False)
    security_id = Column(String, index=True, nullable=True)
    cashflow_date = Column(Date, index=True, nullable=False)
    epoch = Column(Integer, nullable=False, default=0, server_default="0")
    amount = Column(ExactNumeric(18, 10), nullable=False)
    currency = Column(String(3), nullable=False)
    classification = Column(String, nullable=False)
    timing = Column(String, nullable=False)
    calculation_type = Column(String, nullable=False)
    is_position_flow = Column(Boolean, server_default="f", nullable=False)
    is_portfolio_flow = Column(Boolean, server_default="f", nullable=False)
    economic_event_id = Column(String, nullable=True, index=True)
    linked_transaction_group_id = Column(String, nullable=True, index=True)
    calculation_lineage = Column(JSON(none_as_null=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    transaction = relationship("Transaction", back_populates="cashflow")

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_cashflows_amount_finite",
            "amount",
        ),
        UniqueConstraint("transaction_id", "epoch", name="_transaction_epoch_uc"),
        Index(
            "ix_cashflows_portfolio_classification_date",
            "portfolio_id",
            "classification",
            "cashflow_date",
        ),
        Index(
            "ix_cashflows_portfolio_flow_date",
            "portfolio_id",
            "is_portfolio_flow",
            "cashflow_date",
        ),
        Index(
            "ix_cashflows_norm_port_sec_date_epoch",
            func.trim(portfolio_id),
            func.trim(security_id),
            cashflow_date,
            epoch.desc(),
        ),
        Index(
            "ix_cashflows_port_norm_sec_date_epoch",
            "portfolio_id",
            func.trim(security_id),
            cashflow_date,
            epoch.desc(),
        ),
        Index(
            "ix_cashflows_port_txn_epoch_id",
            "portfolio_id",
            "transaction_id",
            epoch.desc(),
            id.desc(),
        ),
    )


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
    original_quantity = Column(ExactNumeric(18, 10), nullable=False)
    open_quantity = Column(ExactNumeric(18, 10), nullable=False)
    lot_cost_local = Column(ExactNumeric(18, 10), nullable=False)
    lot_cost_base = Column(ExactNumeric(18, 10), nullable=False)
    accrued_interest_paid_local = Column(ExactNumeric(18, 10), nullable=False, server_default="0")
    economic_event_id = Column(String, nullable=True, index=True)
    linked_transaction_group_id = Column(String, nullable=True, index=True)
    calculation_policy_id = Column(String, nullable=True)
    calculation_policy_version = Column(String, nullable=True)
    source_system = Column(String, nullable=True)
    amortized_cost_profile_id = Column(String(96), nullable=True)
    amortized_cost_profile_version = Column(Integer, nullable=True)
    amortized_cost_profile_content_hash = Column(String(64), nullable=True)
    amortized_cost_recognized_through = Column(Date, nullable=True)
    amortized_cost_scheduled_local = Column(ExactNumeric(18, 10), nullable=True)
    amortized_book_carrying_local = Column(ExactNumeric(18, 10), nullable=True)
    amortized_book_carrying_base = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_book_fx_rate_to_base = Column(ExactNumeric(18, 10), nullable=True)
    calculation_lineage = Column(JSON(none_as_null=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "lot_id",
            "portfolio_id",
            "security_id",
            name="uq_position_lot_scope_identity",
        ),
        ForeignKeyConstraint(
            [
                "amortized_cost_profile_id",
                "amortized_cost_profile_version",
                "lot_id",
                "portfolio_id",
                "security_id",
            ],
            [
                "lot_amortized_cost_profiles.profile_id",
                "lot_amortized_cost_profiles.profile_version",
                "lot_amortized_cost_profiles.lot_id",
                "lot_amortized_cost_profiles.portfolio_id",
                "lot_amortized_cost_profiles.security_id",
            ],
            name="fk_position_lot_amortized_cost_profile",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "CAST(original_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(open_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(lot_cost_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(lot_cost_base AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(accrued_interest_paid_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_position_lot_state_numeric_finite",
        ),
        CheckConstraint(
            "original_quantity >= 0",
            name="ck_position_lot_original_quantity_nonnegative",
        ),
        CheckConstraint(
            "open_quantity >= 0",
            name="ck_position_lot_open_quantity_nonnegative",
        ),
        CheckConstraint(
            "open_quantity <= original_quantity",
            name="ck_position_lot_open_not_above_original",
        ),
        CheckConstraint(
            "lot_cost_local >= 0",
            name="ck_position_lot_local_cost_nonnegative",
        ),
        CheckConstraint(
            "lot_cost_base >= 0",
            name="ck_position_lot_base_cost_nonnegative",
        ),
        CheckConstraint(
            "accrued_interest_paid_local >= 0",
            name="ck_position_lot_accrued_interest_nonnegative",
        ),
        CheckConstraint(
            "(amortized_cost_profile_id IS NULL "
            "AND amortized_cost_profile_version IS NULL "
            "AND amortized_cost_profile_content_hash IS NULL "
            "AND amortized_cost_recognized_through IS NULL "
            "AND amortized_cost_scheduled_local IS NULL "
            "AND amortized_book_carrying_local IS NULL "
            "AND amortized_book_carrying_base IS NULL "
            "AND amortized_cost_book_fx_rate_to_base IS NULL) OR ("
            "amortized_cost_profile_id IS NOT NULL "
            "AND amortized_cost_profile_version IS NOT NULL "
            "AND amortized_cost_profile_content_hash IS NOT NULL "
            "AND amortized_cost_recognized_through IS NOT NULL "
            "AND amortized_cost_scheduled_local IS NOT NULL "
            "AND amortized_book_carrying_local IS NOT NULL "
            "AND amortized_book_carrying_base IS NOT NULL "
            "AND amortized_cost_book_fx_rate_to_base IS NOT NULL)",
            name="ck_position_lot_amortized_cost_shape",
        ),
        CheckConstraint(
            "amortized_cost_profile_id IS NULL OR ("
            "open_quantity > 0 "
            "AND amortized_cost_profile_version >= 1 "
            "AND amortized_cost_profile_id = btrim(amortized_cost_profile_id) "
            "AND amortized_cost_profile_id <> '' "
            "AND amortized_cost_profile_content_hash ~ '^[0-9a-f]{64}$' "
            "AND amortized_cost_recognized_through >= acquisition_date "
            "AND amortized_cost_scheduled_local >= 0 "
            "AND amortized_book_carrying_local >= 0 "
            "AND amortized_book_carrying_base >= 0 "
            "AND amortized_cost_book_fx_rate_to_base > 0 "
            "AND CAST(amortized_cost_scheduled_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(amortized_book_carrying_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(amortized_book_carrying_base AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(amortized_cost_book_fx_rate_to_base AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity'))",
            name="ck_position_lot_amortized_cost_values",
        ),
        Index(
            "ix_position_lot_norm_port_sec",
            func.trim(portfolio_id),
            func.trim(security_id),
        ),
        Index(
            "ix_position_lot_port_norm_sec_acq_id",
            "portfolio_id",
            func.trim(security_id),
            acquisition_date,
            id,
        ),
        Index(
            "ix_position_lot_port_acq_lot_id",
            "portfolio_id",
            acquisition_date,
            lot_id,
        ),
    )


class LotDisposalReceiptRecord(Base):
    """Append-only versioned receipt for one consuming transaction."""

    __tablename__ = "lot_disposal_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(String(96), nullable=False)
    receipt_version = Column(Integer, nullable=False)
    disposal_transaction_id = Column(
        String,
        ForeignKey("transactions.transaction_id", ondelete="RESTRICT"),
        nullable=False,
    )
    portfolio_id = Column(
        String,
        ForeignKey("portfolios.portfolio_id", ondelete="RESTRICT"),
        nullable=False,
    )
    instrument_id = Column(String, nullable=False)
    security_id = Column(
        String,
        ForeignKey("instruments.security_id", ondelete="RESTRICT"),
        nullable=False,
    )
    disposal_timestamp = Column(DateTime(timezone=True), nullable=False)
    transaction_type = Column(String, nullable=False)
    cost_basis_method = Column(String, nullable=False)
    calculation_policy_id = Column(String, nullable=True)
    calculation_policy_version = Column(String, nullable=True)
    status = Column(String, nullable=False)
    void_reason = Column(String, nullable=True)
    destination_type = Column(String, nullable=True)
    target_transaction_id = Column(String, nullable=True)
    target_lot_id = Column(String, nullable=True)
    target_instrument_id = Column(String, nullable=True)
    external_destination_reference = Column(String, nullable=True)
    consumed_quantity = Column(ExactNumeric(18, 10), nullable=False)
    consumed_cost_local = Column(ExactNumeric(18, 10), nullable=False)
    consumed_cost_base = Column(ExactNumeric(18, 10), nullable=False)
    allocation_count = Column(Integer, nullable=False)
    transaction_calculation_lineage = Column(JSONB(none_as_null=True), nullable=False)
    disposal_calculation_lineage = Column(JSONB(none_as_null=True), nullable=True)
    semantic_content_hash = Column(String(64), nullable=False)
    previous_receipt_content_hash = Column(String(64), nullable=True)
    receipt_content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "receipt_id",
            "receipt_version",
            name="uq_lot_disposal_receipt_version",
        ),
        UniqueConstraint(
            "disposal_transaction_id",
            "receipt_version",
            name="uq_lot_disposal_transaction_version",
        ),
        UniqueConstraint(
            "receipt_id",
            "receipt_version",
            "portfolio_id",
            "security_id",
            name="uq_lot_disposal_receipt_scope_version",
        ),
        CheckConstraint(
            "receipt_version >= 1 AND allocation_count >= 0",
            name="ck_lot_disposal_receipt_counts",
        ),
        CheckConstraint(
            "receipt_id = btrim(receipt_id) AND receipt_id <> '' "
            "AND disposal_transaction_id = btrim(disposal_transaction_id) "
            "AND disposal_transaction_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND instrument_id = btrim(instrument_id) AND instrument_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> '' "
            "AND transaction_type = btrim(transaction_type) AND transaction_type <> ''",
            name="ck_lot_disposal_receipt_identity",
        ),
        CheckConstraint(
            "cost_basis_method IN ('FIFO', 'AVCO')",
            name="ck_lot_disposal_receipt_method",
        ),
        CheckConstraint(
            "(destination_type IS NULL AND target_transaction_id IS NULL "
            "AND target_lot_id IS NULL AND target_instrument_id IS NULL "
            "AND external_destination_reference IS NULL) OR "
            "(destination_type = 'INTERNAL_LOT' "
            "AND target_transaction_id = btrim(target_transaction_id) "
            "AND target_transaction_id <> '' "
            "AND target_lot_id = 'LOT-' || target_transaction_id "
            "AND target_instrument_id = btrim(target_instrument_id) "
            "AND target_instrument_id <> '' AND external_destination_reference IS NULL) OR "
            "(destination_type = 'EXTERNAL_TRANSFER' "
            "AND external_destination_reference = btrim(external_destination_reference) "
            "AND external_destination_reference <> '' AND target_transaction_id IS NULL "
            "AND target_lot_id IS NULL AND target_instrument_id IS NULL)",
            name="ck_lot_disposal_receipt_destination",
        ),
        CheckConstraint(
            "(calculation_policy_id IS NULL AND calculation_policy_version IS NULL) "
            "OR (calculation_policy_id = btrim(calculation_policy_id) "
            "AND calculation_policy_id <> '' "
            "AND calculation_policy_version = btrim(calculation_policy_version) "
            "AND calculation_policy_version <> '')",
            name="ck_lot_disposal_receipt_policy",
        ),
        _finite_numeric_check_constraint(
            "ck_lot_disposal_receipt_amounts_finite",
            "consumed_quantity",
            "consumed_cost_local",
            "consumed_cost_base",
        ),
        CheckConstraint(
            "consumed_quantity >= 0 AND consumed_cost_local >= 0 AND consumed_cost_base >= 0",
            name="ck_lot_disposal_receipt_amounts_nonnegative",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND void_reason IS NULL "
            "AND consumed_quantity > 0 AND allocation_count > 0 "
            "AND disposal_calculation_lineage IS NOT NULL) "
            "OR (status = 'VOIDED' AND void_reason = btrim(void_reason) "
            "AND void_reason <> '' AND consumed_quantity = 0 "
            "AND consumed_cost_local = 0 AND consumed_cost_base = 0 "
            "AND allocation_count = 0 AND disposal_calculation_lineage IS NULL)",
            name="ck_lot_disposal_receipt_lifecycle",
        ),
        CheckConstraint(
            "jsonb_typeof(transaction_calculation_lineage) = 'object' "
            "AND (disposal_calculation_lineage IS NULL "
            "OR jsonb_typeof(disposal_calculation_lineage) = 'object')",
            name="ck_lot_disposal_receipt_lineage",
        ),
        CheckConstraint(
            "semantic_content_hash ~ '^[0-9a-f]{64}$' "
            "AND receipt_content_hash ~ '^[0-9a-f]{64}$' "
            "AND (previous_receipt_content_hash IS NULL "
            "OR previous_receipt_content_hash ~ '^[0-9a-f]{64}$')",
            name="ck_lot_disposal_receipt_hashes",
        ),
        CheckConstraint(
            "(receipt_version = 1 AND previous_receipt_content_hash IS NULL) "
            "OR (receipt_version > 1 AND previous_receipt_content_hash IS NOT NULL)",
            name="ck_lot_disposal_receipt_chain",
        ),
        Index(
            "ix_lot_disposal_receipt_scope_time",
            "portfolio_id",
            "security_id",
            disposal_timestamp.desc(),
            receipt_version.desc(),
        ),
        Index(
            "ix_lot_disposal_receipt_tx_version",
            "disposal_transaction_id",
            receipt_version.desc(),
        ),
        Index(
            "ix_lot_disposal_receipt_target_tx_version",
            "portfolio_id",
            "target_transaction_id",
            receipt_version.desc(),
        ),
        Index(
            "ix_lot_disposal_receipt_external_destination",
            "portfolio_id",
            "external_destination_reference",
        ),
    )


class LotDisposalAllocationRecord(Base):
    """Immutable ordered source-lot contribution to one receipt version."""

    __tablename__ = "lot_disposal_allocations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(String(96), nullable=False)
    receipt_version = Column(Integer, nullable=False)
    portfolio_id = Column(String, nullable=False)
    security_id = Column(String, nullable=False)
    allocation_ordinal = Column(Integer, nullable=False)
    source_lot_id = Column(String, nullable=False)
    source_transaction_id = Column(String, nullable=False)
    source_acquisition_date = Column(Date, nullable=False)
    consumed_quantity = Column(ExactNumeric(18, 10), nullable=False)
    consumed_cost_local = Column(ExactNumeric(18, 10), nullable=False)
    consumed_cost_base = Column(ExactNumeric(18, 10), nullable=False)
    amortized_cost_profile_id = Column(String(96), nullable=True)
    amortized_cost_profile_version = Column(Integer, nullable=True)
    amortized_cost_profile_content_hash = Column(String(64), nullable=True)
    amortized_cost_currency = Column(String(3), nullable=True)
    amortized_cost_recognized_through = Column(Date, nullable=True)
    amortized_cost_original_quantity = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_open_quantity_before = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_residual_quantity = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_scheduled_local = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_current_local = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_current_base = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_residual_local = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_book_fx_rate_to_base = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_residual_base = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_retained_rounding_local = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_retained_rounding_base = Column(ExactNumeric(18, 10), nullable=True)
    amortized_cost_calculation_lineage = Column(JSONB(none_as_null=True), nullable=True)
    allocation_content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_id", "receipt_version", "portfolio_id", "security_id"],
            [
                "lot_disposal_receipts.receipt_id",
                "lot_disposal_receipts.receipt_version",
                "lot_disposal_receipts.portfolio_id",
                "lot_disposal_receipts.security_id",
            ],
            name="fk_lot_disposal_allocation_receipt",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "amortized_cost_profile_id",
                "amortized_cost_profile_version",
                "source_lot_id",
                "portfolio_id",
                "security_id",
            ],
            [
                "lot_amortized_cost_profiles.profile_id",
                "lot_amortized_cost_profiles.profile_version",
                "lot_amortized_cost_profiles.lot_id",
                "lot_amortized_cost_profiles.portfolio_id",
                "lot_amortized_cost_profiles.security_id",
            ],
            name="fk_lot_disposal_allocation_amort_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_transaction_id"],
            ["transactions.transaction_id"],
            name="fk_lot_disposal_allocation_source_tx",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_lot_id", "portfolio_id", "security_id"],
            [
                "position_lot_state.lot_id",
                "position_lot_state.portfolio_id",
                "position_lot_state.security_id",
            ],
            name="fk_lot_disposal_allocation_lot_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "receipt_id",
            "receipt_version",
            "allocation_ordinal",
            name="uq_lot_disposal_allocation_ordinal",
        ),
        UniqueConstraint(
            "receipt_id",
            "receipt_version",
            "source_lot_id",
            name="uq_lot_disposal_allocation_source_lot",
        ),
        CheckConstraint(
            "receipt_version >= 1 AND allocation_ordinal >= 1",
            name="ck_lot_disposal_allocation_identity",
        ),
        CheckConstraint(
            "receipt_id = btrim(receipt_id) AND receipt_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> '' "
            "AND source_lot_id = btrim(source_lot_id) AND source_lot_id <> '' "
            "AND source_transaction_id = btrim(source_transaction_id) "
            "AND source_transaction_id <> ''",
            name="ck_lot_disposal_allocation_scope",
        ),
        _finite_numeric_check_constraint(
            "ck_lot_disposal_allocation_amounts_finite",
            "consumed_quantity",
            "consumed_cost_local",
            "consumed_cost_base",
        ),
        CheckConstraint(
            "consumed_quantity > 0 AND consumed_cost_local >= 0 AND consumed_cost_base >= 0",
            name="ck_lot_disposal_allocation_amounts",
        ),
        CheckConstraint(
            "allocation_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_disposal_allocation_hash",
        ),
        CheckConstraint(
            "(amortized_cost_profile_id IS NULL "
            "AND amortized_cost_profile_version IS NULL "
            "AND amortized_cost_profile_content_hash IS NULL "
            "AND amortized_cost_currency IS NULL "
            "AND amortized_cost_recognized_through IS NULL "
            "AND amortized_cost_original_quantity IS NULL "
            "AND amortized_cost_open_quantity_before IS NULL "
            "AND amortized_cost_residual_quantity IS NULL "
            "AND amortized_cost_scheduled_local IS NULL "
            "AND amortized_cost_current_local IS NULL "
            "AND amortized_cost_current_base IS NULL "
            "AND amortized_cost_residual_local IS NULL "
            "AND amortized_cost_book_fx_rate_to_base IS NULL "
            "AND amortized_cost_residual_base IS NULL "
            "AND amortized_cost_retained_rounding_local IS NULL "
            "AND amortized_cost_retained_rounding_base IS NULL "
            "AND amortized_cost_calculation_lineage IS NULL) OR ("
            "amortized_cost_profile_id IS NOT NULL "
            "AND amortized_cost_profile_version IS NOT NULL "
            "AND amortized_cost_profile_content_hash IS NOT NULL "
            "AND amortized_cost_currency IS NOT NULL "
            "AND amortized_cost_recognized_through IS NOT NULL "
            "AND amortized_cost_original_quantity IS NOT NULL "
            "AND amortized_cost_open_quantity_before IS NOT NULL "
            "AND amortized_cost_residual_quantity IS NOT NULL "
            "AND amortized_cost_scheduled_local IS NOT NULL "
            "AND amortized_cost_current_local IS NOT NULL "
            "AND amortized_cost_current_base IS NOT NULL "
            "AND amortized_cost_residual_local IS NOT NULL "
            "AND amortized_cost_book_fx_rate_to_base IS NOT NULL "
            "AND amortized_cost_residual_base IS NOT NULL "
            "AND amortized_cost_retained_rounding_local IS NOT NULL "
            "AND amortized_cost_retained_rounding_base IS NOT NULL "
            "AND amortized_cost_calculation_lineage IS NOT NULL)",
            name="ck_lot_disposal_allocation_amort_shape",
        ),
        _finite_numeric_check_constraint(
            "ck_lot_disposal_allocation_amort_finite",
            "amortized_cost_original_quantity",
            "amortized_cost_open_quantity_before",
            "amortized_cost_residual_quantity",
            "amortized_cost_scheduled_local",
            "amortized_cost_current_local",
            "amortized_cost_current_base",
            "amortized_cost_residual_local",
            "amortized_cost_book_fx_rate_to_base",
            "amortized_cost_residual_base",
            "amortized_cost_retained_rounding_local",
            "amortized_cost_retained_rounding_base",
        ),
        CheckConstraint(
            "amortized_cost_profile_id IS NULL OR ("
            "amortized_cost_profile_version >= 1 "
            "AND amortized_cost_profile_id = btrim(amortized_cost_profile_id) "
            "AND amortized_cost_profile_id <> '' "
            "AND amortized_cost_profile_content_hash ~ '^[0-9a-f]{64}$' "
            "AND amortized_cost_currency ~ '^[A-Z]{3}$' "
            "AND amortized_cost_original_quantity > 0 "
            "AND amortized_cost_open_quantity_before > 0 "
            "AND amortized_cost_open_quantity_before <= amortized_cost_original_quantity "
            "AND amortized_cost_residual_quantity >= 0 "
            "AND amortized_cost_scheduled_local >= 0 "
            "AND amortized_cost_current_local >= 0 "
            "AND amortized_cost_current_base >= 0 "
            "AND amortized_cost_residual_local >= 0 "
            "AND amortized_cost_book_fx_rate_to_base > 0 "
            "AND amortized_cost_residual_base >= 0 "
            "AND jsonb_typeof(amortized_cost_calculation_lineage) = 'object')",
            name="ck_lot_disposal_allocation_amort_values",
        ),
        Index(
            "ix_lot_disposal_allocation_source",
            "portfolio_id",
            "security_id",
            "source_lot_id",
            "source_acquisition_date",
        ),
    )


class LotBasisTransferReceiptRecord(Base):
    """Append-only versioned receipt for one basis-only lot movement."""

    __tablename__ = "lot_basis_transfer_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(String(96), nullable=False)
    receipt_version = Column(Integer, nullable=False)
    source_transaction_id = Column(
        String,
        ForeignKey("transactions.transaction_id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_transaction_id = Column(String, nullable=False)
    target_lot_id = Column(String, nullable=False)
    portfolio_id = Column(
        String,
        ForeignKey("portfolios.portfolio_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_instrument_id = Column(String, nullable=False)
    source_security_id = Column(
        String,
        ForeignKey("instruments.security_id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_instrument_id = Column(String, nullable=True)
    transfer_timestamp = Column(DateTime(timezone=True), nullable=False)
    transaction_type = Column(String, nullable=False)
    cost_basis_method = Column(String, nullable=False)
    calculation_policy_id = Column(String, nullable=True)
    calculation_policy_version = Column(String, nullable=True)
    status = Column(String, nullable=False)
    void_reason = Column(String, nullable=True)
    transferred_cost_local = Column(ExactNumeric(18, 10), nullable=False)
    transferred_cost_base = Column(ExactNumeric(18, 10), nullable=False)
    allocation_count = Column(Integer, nullable=False)
    transaction_calculation_lineage = Column(JSONB(none_as_null=True), nullable=False)
    basis_transfer_calculation_lineage = Column(JSONB(none_as_null=True), nullable=True)
    semantic_content_hash = Column(String(64), nullable=False)
    previous_receipt_content_hash = Column(String(64), nullable=True)
    receipt_content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "receipt_id",
            "receipt_version",
            name="uq_lot_basis_transfer_receipt_version",
        ),
        UniqueConstraint(
            "source_transaction_id",
            "receipt_version",
            name="uq_lot_basis_transfer_source_tx_version",
        ),
        UniqueConstraint(
            "receipt_id",
            "receipt_version",
            "portfolio_id",
            "source_security_id",
            name="uq_lot_basis_transfer_receipt_scope_version",
        ),
        CheckConstraint(
            "receipt_version >= 1 AND allocation_count >= 0",
            name="ck_lot_basis_transfer_receipt_counts",
        ),
        CheckConstraint(
            "receipt_id = btrim(receipt_id) AND receipt_id <> '' "
            "AND source_transaction_id = btrim(source_transaction_id) "
            "AND source_transaction_id <> '' "
            "AND target_transaction_id = btrim(target_transaction_id) "
            "AND target_transaction_id <> '' "
            "AND target_lot_id = 'LOT-' || target_transaction_id "
            "AND source_transaction_id <> target_transaction_id "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND source_instrument_id = btrim(source_instrument_id) "
            "AND source_instrument_id <> '' "
            "AND source_security_id = btrim(source_security_id) "
            "AND source_security_id <> '' "
            "AND (target_instrument_id IS NULL OR "
            "(target_instrument_id = btrim(target_instrument_id) AND target_instrument_id <> '')) "
            "AND transaction_type = btrim(transaction_type) AND transaction_type <> ''",
            name="ck_lot_basis_transfer_receipt_identity",
        ),
        CheckConstraint(
            "cost_basis_method IN ('FIFO', 'AVCO')",
            name="ck_lot_basis_transfer_receipt_method",
        ),
        CheckConstraint(
            "(calculation_policy_id IS NULL AND calculation_policy_version IS NULL) "
            "OR (calculation_policy_id = btrim(calculation_policy_id) "
            "AND calculation_policy_id <> '' "
            "AND calculation_policy_version = btrim(calculation_policy_version) "
            "AND calculation_policy_version <> '')",
            name="ck_lot_basis_transfer_receipt_policy",
        ),
        _finite_numeric_check_constraint(
            "ck_lot_basis_transfer_receipt_amounts_finite",
            "transferred_cost_local",
            "transferred_cost_base",
        ),
        CheckConstraint(
            "transferred_cost_local >= 0 AND transferred_cost_base >= 0",
            name="ck_lot_basis_transfer_receipt_amounts_nonnegative",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND void_reason IS NULL AND allocation_count > 0 "
            "AND (transferred_cost_local > 0 OR transferred_cost_base > 0) "
            "AND basis_transfer_calculation_lineage IS NOT NULL) "
            "OR (status = 'VOIDED' AND void_reason = btrim(void_reason) "
            "AND void_reason <> '' AND transferred_cost_local = 0 "
            "AND transferred_cost_base = 0 AND allocation_count = 0 "
            "AND basis_transfer_calculation_lineage IS NULL)",
            name="ck_lot_basis_transfer_receipt_lifecycle",
        ),
        CheckConstraint(
            "jsonb_typeof(transaction_calculation_lineage) = 'object' "
            "AND (basis_transfer_calculation_lineage IS NULL "
            "OR jsonb_typeof(basis_transfer_calculation_lineage) = 'object')",
            name="ck_lot_basis_transfer_receipt_lineage",
        ),
        CheckConstraint(
            "semantic_content_hash ~ '^[0-9a-f]{64}$' "
            "AND receipt_content_hash ~ '^[0-9a-f]{64}$' "
            "AND (previous_receipt_content_hash IS NULL "
            "OR previous_receipt_content_hash ~ '^[0-9a-f]{64}$')",
            name="ck_lot_basis_transfer_receipt_hashes",
        ),
        CheckConstraint(
            "(receipt_version = 1 AND previous_receipt_content_hash IS NULL) "
            "OR (receipt_version > 1 AND previous_receipt_content_hash IS NOT NULL)",
            name="ck_lot_basis_transfer_receipt_chain",
        ),
        Index(
            "ix_lot_basis_transfer_receipt_scope_time",
            "portfolio_id",
            "source_security_id",
            transfer_timestamp.desc(),
            receipt_version.desc(),
        ),
        Index(
            "ix_lot_basis_transfer_receipt_source_tx_version",
            "source_transaction_id",
            receipt_version.desc(),
        ),
        Index(
            "ix_lot_basis_transfer_receipt_target_tx_version",
            "portfolio_id",
            "target_transaction_id",
            receipt_version.desc(),
        ),
    )


class LotBasisTransferAllocationRecord(Base):
    """Immutable ordered source-lot contribution to one basis transfer version."""

    __tablename__ = "lot_basis_transfer_allocations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(String(96), nullable=False)
    receipt_version = Column(Integer, nullable=False)
    portfolio_id = Column(String, nullable=False)
    source_security_id = Column(String, nullable=False)
    allocation_ordinal = Column(Integer, nullable=False)
    source_lot_id = Column(String, nullable=False)
    source_transaction_id = Column(String, nullable=False)
    source_acquisition_date = Column(Date, nullable=False)
    retained_quantity = Column(ExactNumeric(18, 10), nullable=False)
    source_cost_local_before = Column(ExactNumeric(18, 10), nullable=False)
    source_cost_base_before = Column(ExactNumeric(18, 10), nullable=False)
    transferred_cost_local = Column(ExactNumeric(18, 10), nullable=False)
    transferred_cost_base = Column(ExactNumeric(18, 10), nullable=False)
    retained_cost_local = Column(ExactNumeric(18, 10), nullable=False)
    retained_cost_base = Column(ExactNumeric(18, 10), nullable=False)
    allocation_content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_id", "receipt_version", "portfolio_id", "source_security_id"],
            [
                "lot_basis_transfer_receipts.receipt_id",
                "lot_basis_transfer_receipts.receipt_version",
                "lot_basis_transfer_receipts.portfolio_id",
                "lot_basis_transfer_receipts.source_security_id",
            ],
            name="fk_lot_basis_transfer_allocation_receipt",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_transaction_id"],
            ["transactions.transaction_id"],
            name="fk_lot_basis_transfer_allocation_source_tx",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_lot_id", "portfolio_id", "source_security_id"],
            [
                "position_lot_state.lot_id",
                "position_lot_state.portfolio_id",
                "position_lot_state.security_id",
            ],
            name="fk_lot_basis_transfer_allocation_lot_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "receipt_id",
            "receipt_version",
            "allocation_ordinal",
            name="uq_lot_basis_transfer_allocation_ordinal",
        ),
        UniqueConstraint(
            "receipt_id",
            "receipt_version",
            "source_lot_id",
            name="uq_lot_basis_transfer_allocation_source_lot",
        ),
        CheckConstraint(
            "receipt_version >= 1 AND allocation_ordinal >= 1",
            name="ck_lot_basis_transfer_allocation_identity",
        ),
        CheckConstraint(
            "receipt_id = btrim(receipt_id) AND receipt_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND source_security_id = btrim(source_security_id) "
            "AND source_security_id <> '' "
            "AND source_lot_id = btrim(source_lot_id) AND source_lot_id <> '' "
            "AND source_transaction_id = btrim(source_transaction_id) "
            "AND source_transaction_id <> ''",
            name="ck_lot_basis_transfer_allocation_scope",
        ),
        _finite_numeric_check_constraint(
            "ck_lot_basis_transfer_allocation_amounts_finite",
            "retained_quantity",
            "source_cost_local_before",
            "source_cost_base_before",
            "transferred_cost_local",
            "transferred_cost_base",
            "retained_cost_local",
            "retained_cost_base",
        ),
        CheckConstraint(
            "retained_quantity > 0 AND source_cost_local_before >= 0 "
            "AND source_cost_base_before >= 0 AND transferred_cost_local >= 0 "
            "AND transferred_cost_base >= 0 AND retained_cost_local >= 0 "
            "AND retained_cost_base >= 0 "
            "AND (transferred_cost_local > 0 OR transferred_cost_base > 0) "
            "AND source_cost_local_before = transferred_cost_local + retained_cost_local "
            "AND source_cost_base_before = transferred_cost_base + retained_cost_base",
            name="ck_lot_basis_transfer_allocation_conservation",
        ),
        CheckConstraint(
            "allocation_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_basis_transfer_allocation_hash",
        ),
        Index(
            "ix_lot_basis_transfer_allocation_source",
            "portfolio_id",
            "source_security_id",
            "source_lot_id",
            "source_acquisition_date",
        ),
    )


class LotAmortizedCostAuthorityRecord(Base):
    """Append-only source authority used to calculate lot amortized cost."""

    __tablename__ = "lot_amortized_cost_authority"

    id = Column(Integer, primary_key=True, autoincrement=True)
    authority_type = Column(String, nullable=False)
    tenant_id = Column(String, nullable=False)
    legal_book_id = Column(String, nullable=False)
    portfolio_id = Column(String, nullable=False)
    security_id = Column(String, nullable=False)
    lot_id = Column(String, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    lifecycle_status = Column(String, nullable=False)
    source_version = Column(Integer, nullable=False)
    source_system = Column(String, nullable=False)
    source_record_id = Column(String, nullable=False)
    source_revision = Column(String, nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    authority_content_hash = Column(String(64), nullable=False)
    authority_payload = Column(JSONB(none_as_null=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "legal_book_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.legal_book_id", "portfolios.portfolio_id"],
            name="fk_lot_amort_authority_book_scope",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["instruments.security_id"],
            name="fk_lot_amort_authority_security",
        ),
        ForeignKeyConstraint(
            ["lot_id", "portfolio_id", "security_id"],
            [
                "position_lot_state.lot_id",
                "position_lot_state.portfolio_id",
                "position_lot_state.security_id",
            ],
            name="fk_lot_amort_authority_lot_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "authority_type",
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            "security_id",
            "lot_id",
            "source_system",
            "source_record_id",
            "source_version",
            name="uq_lot_amort_authority_source_version",
        ),
        CheckConstraint(
            "authority_type IN ('POLICY_ASSIGNMENT', 'CLEAN_COST_BASIS', "
            "'AMORTIZATION_SCHEDULE', 'EFFECTIVE_YIELD')",
            name="ck_lot_amort_authority_type",
        ),
        CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' "
            "AND legal_book_id = btrim(legal_book_id) AND legal_book_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> '' "
            "AND lot_id = btrim(lot_id) AND lot_id <> ''",
            name="ck_lot_amort_authority_scope_normalized",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_lot_amort_authority_effective_window",
        ),
        CheckConstraint(
            "lifecycle_status IN ('ACTIVE', 'SUSPENDED', 'RETIRED')",
            name="ck_lot_amort_authority_status",
        ),
        CheckConstraint(
            "source_version >= 1",
            name="ck_lot_amort_authority_version_positive",
        ),
        CheckConstraint(
            "source_system = btrim(source_system) AND source_system <> '' "
            "AND source_record_id = btrim(source_record_id) AND source_record_id <> '' "
            "AND source_revision = btrim(source_revision) AND source_revision <> ''",
            name="ck_lot_amort_authority_source_normalized",
        ),
        CheckConstraint(
            "authority_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_amort_authority_hash",
        ),
        CheckConstraint(
            "jsonb_typeof(authority_payload) = 'object'",
            name="ck_lot_amort_authority_payload_object",
        ),
        Index(
            "ix_lot_amort_authority_scope_effective",
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            "security_id",
            "lot_id",
            "authority_type",
            "valid_from",
            "valid_to",
        ),
        Index(
            "ix_lot_amort_authority_source_history",
            "source_system",
            "source_record_id",
            source_version.desc(),
        ),
    )


class LotAmortizedCostProfileRecord(Base):
    """Append-only lot amortized-cost profile header and audit evidence."""

    __tablename__ = "lot_amortized_cost_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(String(96), nullable=False)
    profile_version = Column(Integer, nullable=False)
    tenant_id = Column(String, nullable=False)
    legal_book_id = Column(String, nullable=False)
    portfolio_id = Column(String, nullable=False)
    security_id = Column(String, ForeignKey("instruments.security_id"), nullable=False)
    lot_id = Column(String, nullable=False)
    effective_date = Column(Date, nullable=False)
    status = Column(String, nullable=False)
    eligibility_reason = Column(String, nullable=True)
    policy_id = Column(String, nullable=True)
    policy_version = Column(Integer, nullable=True)
    schedule_version = Column(Integer, nullable=True)
    currency = Column(String(3), nullable=True)
    direction = Column(String, nullable=True)
    initial_amortized_cost_local = Column(ExactNumeric(18, 10), nullable=True)
    redemption_value_local = Column(ExactNumeric(18, 10), nullable=True)
    final_amortized_cost_local = Column(ExactNumeric(18, 10), nullable=True)
    residual_local = Column(ExactNumeric(18, 10), nullable=True)
    authority_content_hash = Column(String(64), nullable=True)
    source_references = Column(JSONB(none_as_null=True), nullable=False)
    calculation_lineage = Column(JSONB(none_as_null=True), nullable=True)
    profile_content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "profile_version",
            name="uq_lot_amort_profile_version",
        ),
        UniqueConstraint(
            "profile_id",
            "profile_version",
            "lot_id",
            "portfolio_id",
            "security_id",
            name="uq_lot_amort_profile_allocation_scope",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "legal_book_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.legal_book_id", "portfolios.portfolio_id"],
            name="fk_lot_amort_profile_book_scope",
        ),
        ForeignKeyConstraint(
            ["lot_id", "portfolio_id", "security_id"],
            [
                "position_lot_state.lot_id",
                "position_lot_state.portfolio_id",
                "position_lot_state.security_id",
            ],
            name="fk_lot_amort_profile_lot_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "profile_version >= 1",
            name="ck_lot_amort_profile_version_positive",
        ),
        CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' "
            "AND legal_book_id = btrim(legal_book_id) AND legal_book_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> '' "
            "AND lot_id = btrim(lot_id) AND lot_id <> ''",
            name="ck_lot_amort_profile_scope_normalized",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'PARKED', 'INELIGIBLE')",
            name="ck_lot_amort_profile_status",
        ),
        CheckConstraint(
            "direction IS NULL OR direction IN "
            "('PREMIUM_AMORTIZATION', 'DISCOUNT_ACCRETION', 'AT_PAR')",
            name="ck_lot_amort_profile_direction",
        ),
        CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_lot_amort_profile_currency",
        ),
        CheckConstraint(
            "policy_version IS NULL OR policy_version >= 1",
            name="ck_lot_amort_profile_policy_version",
        ),
        CheckConstraint(
            "schedule_version IS NULL OR schedule_version >= 1",
            name="ck_lot_amort_profile_schedule_version",
        ),
        _finite_numeric_check_constraint(
            "ck_lot_amort_profile_amounts_finite",
            "initial_amortized_cost_local",
            "redemption_value_local",
            "final_amortized_cost_local",
            "residual_local",
        ),
        CheckConstraint(
            "initial_amortized_cost_local >= 0",
            name="ck_lot_amort_profile_initial_nonnegative",
        ),
        CheckConstraint(
            "redemption_value_local >= 0",
            name="ck_lot_amort_profile_redemption_nonnegative",
        ),
        CheckConstraint(
            "final_amortized_cost_local >= 0",
            name="ck_lot_amort_profile_final_nonnegative",
        ),
        CheckConstraint(
            "authority_content_hash IS NULL OR authority_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_amort_profile_authority_hash",
        ),
        CheckConstraint(
            "profile_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_amort_profile_content_hash",
        ),
        CheckConstraint(
            "jsonb_typeof(source_references) = 'array'",
            name="ck_lot_amort_profile_sources_array",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND eligibility_reason IS NULL "
            "AND policy_id IS NOT NULL AND policy_version IS NOT NULL "
            "AND schedule_version IS NOT NULL AND currency IS NOT NULL "
            "AND direction IS NOT NULL AND initial_amortized_cost_local IS NOT NULL "
            "AND redemption_value_local IS NOT NULL "
            "AND final_amortized_cost_local IS NOT NULL AND residual_local IS NOT NULL "
            "AND authority_content_hash IS NOT NULL AND calculation_lineage IS NOT NULL "
            "AND jsonb_array_length(source_references) > 0) "
            "OR (status IN ('PARKED', 'INELIGIBLE') AND eligibility_reason IS NOT NULL "
            "AND direction IS NULL AND initial_amortized_cost_local IS NULL "
            "AND redemption_value_local IS NULL AND final_amortized_cost_local IS NULL "
            "AND residual_local IS NULL AND calculation_lineage IS NULL)",
            name="ck_lot_amort_profile_lifecycle_shape",
        ),
        Index(
            "ix_lot_amort_profile_scope_version",
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            "security_id",
            "lot_id",
            profile_version.desc(),
        ),
        Index(
            "ix_lot_amort_profile_parked_effective",
            "status",
            "effective_date",
            "profile_id",
            postgresql_where=text("status IN ('PARKED', 'INELIGIBLE')"),
        ),
        Index(
            "ix_lot_amort_profile_id_effective_version",
            "profile_id",
            effective_date.desc(),
            profile_version.desc(),
        ),
    )


class LotAmortizedCostPeriodRecord(Base):
    """Immutable normalized period row for one lot amortized-cost profile version."""

    __tablename__ = "lot_amortized_cost_periods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(String(96), nullable=False)
    profile_version = Column(Integer, nullable=False)
    period_ordinal = Column(Integer, nullable=False)
    period_start_date = Column(Date, nullable=False)
    period_end_date = Column(Date, nullable=False)
    year_fraction = Column(ExactNumeric(), nullable=False)
    period_rate = Column(ExactNumeric(), nullable=True)
    begin_amortized_cost_local = Column(ExactNumeric(18, 10), nullable=False)
    interest_income_local = Column(ExactNumeric(18, 10), nullable=False)
    cash_coupon_local = Column(ExactNumeric(18, 10), nullable=False)
    amortization_amount_local = Column(ExactNumeric(18, 10), nullable=False)
    end_amortized_cost_local = Column(ExactNumeric(18, 10), nullable=False)
    rounding_adjustment_local = Column(ExactNumeric(18, 10), nullable=False)
    calculation_output_hash = Column(String(64), nullable=False)
    period_content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "profile_version"],
            [
                "lot_amortized_cost_profiles.profile_id",
                "lot_amortized_cost_profiles.profile_version",
            ],
            name="fk_lot_amort_period_profile_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "profile_id",
            "profile_version",
            "period_ordinal",
            name="uq_lot_amort_period_ordinal",
        ),
        CheckConstraint(
            "profile_version >= 1 AND period_ordinal >= 1",
            name="ck_lot_amort_period_identity_positive",
        ),
        CheckConstraint(
            "period_end_date > period_start_date",
            name="ck_lot_amort_period_date_order",
        ),
        _finite_numeric_check_constraint(
            "ck_lot_amort_period_amounts_finite",
            "year_fraction",
            "period_rate",
            "begin_amortized_cost_local",
            "interest_income_local",
            "cash_coupon_local",
            "amortization_amount_local",
            "end_amortized_cost_local",
            "rounding_adjustment_local",
        ),
        CheckConstraint(
            "year_fraction > 0 AND begin_amortized_cost_local >= 0 "
            "AND cash_coupon_local >= 0 AND end_amortized_cost_local >= 0",
            name="ck_lot_amort_period_amounts_governed",
        ),
        CheckConstraint(
            "calculation_output_hash ~ '^[0-9a-f]{64}$' AND period_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_amort_period_hashes",
        ),
        Index(
            "ix_lot_amort_period_profile_end",
            "profile_id",
            profile_version.desc(),
            "period_end_date",
        ),
    )


class CostBasisProcessingState(Base):
    """Durable ordering watermark for incremental cost-basis processing."""

    __tablename__ = "cost_basis_processing_state"

    portfolio_id = Column(
        String,
        ForeignKey("portfolios.portfolio_id"),
        primary_key=True,
        nullable=False,
    )
    security_id = Column(String, primary_key=True, nullable=False)
    cost_basis_method = Column(String, nullable=False)
    latest_transaction_date = Column(DateTime(timezone=True), nullable=False)
    latest_dependency_rank = Column(Integer, nullable=False)
    latest_cash_dependency_rank = Column(Integer, nullable=False)
    latest_child_sequence = Column(Integer, nullable=False)
    latest_target_instrument_id = Column(String, nullable=False, server_default="")
    latest_quantity = Column(ExactNumeric(18, 10), nullable=False)
    latest_transaction_id = Column(String, nullable=False)
    engine_state_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "CAST(latest_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_cost_basis_processing_quantity_finite",
        ),
        CheckConstraint(
            "latest_quantity >= 0",
            name="ck_cost_basis_processing_quantity_nonnegative",
        ),
        Index(
            "ix_cost_basis_processing_state_updated_key",
            updated_at.desc(),
            portfolio_id,
            security_id,
        ),
    )


class AverageCostPoolState(Base):
    """Durable AVCO aggregate used for bounded ordered processing."""

    __tablename__ = "average_cost_pool_state"

    portfolio_id = Column(
        String,
        ForeignKey("portfolios.portfolio_id"),
        primary_key=True,
        nullable=False,
    )
    security_id = Column(String, primary_key=True, nullable=False)
    instrument_id = Column(String, nullable=False)
    representative_source_transaction_id = Column(
        String,
        ForeignKey("transactions.transaction_id"),
        nullable=True,
    )
    pool_quantity = Column(ExactNumeric(18, 10), nullable=False)
    pool_cost_local = Column(ExactNumeric(18, 10), nullable=False)
    pool_cost_base = Column(ExactNumeric(18, 10), nullable=False)
    state_version = Column(String, nullable=False)
    calculation_lineage = Column(JSON(none_as_null=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "CAST(pool_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(pool_cost_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(pool_cost_base AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_average_cost_pool_numeric_finite",
        ),
        CheckConstraint(
            "pool_quantity >= 0",
            name="ck_average_cost_pool_state_quantity_nonnegative",
        ),
        CheckConstraint(
            "pool_cost_local >= 0",
            name="ck_average_cost_pool_state_local_cost_nonnegative",
        ),
        CheckConstraint(
            "pool_cost_base >= 0",
            name="ck_average_cost_pool_state_base_cost_nonnegative",
        ),
        CheckConstraint(
            "pool_quantity = 0 OR representative_source_transaction_id IS NOT NULL",
            name="ck_average_cost_pool_state_positive_source",
        ),
        Index(
            "ix_average_cost_pool_state_updated_key",
            updated_at.desc(),
            portfolio_id,
            security_id,
        ),
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
    accrued_interest_paid_local = Column(ExactNumeric(18, 10), nullable=False, server_default="0")
    remaining_offset_local = Column(ExactNumeric(18, 10), nullable=False, server_default="0")
    economic_event_id = Column(String, nullable=True, index=True)
    linked_transaction_group_id = Column(String, nullable=True, index=True)
    calculation_policy_id = Column(String, nullable=True)
    calculation_policy_version = Column(String, nullable=True)
    source_system = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "CAST(accrued_interest_paid_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(remaining_offset_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_accrued_income_offset_numeric_finite",
        ),
        CheckConstraint(
            "accrued_interest_paid_local >= 0",
            name="ck_accrued_income_paid_nonnegative",
        ),
        CheckConstraint(
            "remaining_offset_local >= 0",
            name="ck_accrued_income_remaining_nonnegative",
        ),
        Index(
            "ix_accrued_offset_port_norm_sec_id",
            "portfolio_id",
            func.trim(security_id),
            id,
        ),
    )


class PositionTimeseries(Base):
    __tablename__ = "position_timeseries"

    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), primary_key=True)
    security_id = Column(String, ForeignKey("instruments.security_id"), primary_key=True)
    date = Column(Date, primary_key=True)
    epoch = Column(Integer, primary_key=True, default=0, server_default="0")
    bod_market_value = Column(ExactNumeric(18, 10), nullable=False)
    bod_cashflow_position = Column(ExactNumeric(18, 10), nullable=False)
    eod_cashflow_position = Column(ExactNumeric(18, 10), nullable=False)
    bod_cashflow_portfolio = Column(ExactNumeric(18, 10), nullable=False)
    eod_cashflow_portfolio = Column(ExactNumeric(18, 10), nullable=False)
    eod_market_value = Column(ExactNumeric(18, 10), nullable=False)
    fees = Column(ExactNumeric(18, 10), default=0, nullable=False)
    quantity = Column(ExactNumeric(18, 10), nullable=False)
    cost = Column(ExactNumeric(18, 10), nullable=False)
    calculation_lineage = Column(JSON(none_as_null=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_position_timeseries_values_finite",
            "bod_market_value",
            "bod_cashflow_position",
            "eod_cashflow_position",
            "bod_cashflow_portfolio",
            "eod_cashflow_portfolio",
            "eod_market_value",
            "fees",
            "quantity",
            "cost",
        ),
        Index(
            "ix_pos_ts_norm_port_sec_date_epoch",
            func.trim(portfolio_id),
            func.trim(security_id),
            date.desc(),
            epoch.desc(),
        ),
        Index(
            "ix_pos_ts_port_date_norm_sec_epoch",
            "portfolio_id",
            date,
            func.trim(security_id),
            epoch.desc(),
        ),
        Index(
            "ix_pos_ts_port_norm_sec_date_epoch",
            "portfolio_id",
            func.trim(security_id),
            date.desc(),
            epoch.desc(),
        ),
    )


class PortfolioTimeseries(Base):
    __tablename__ = "portfolio_timeseries"

    portfolio_id = Column(String, ForeignKey("portfolios.portfolio_id"), primary_key=True)
    date = Column(Date, primary_key=True)
    epoch = Column(Integer, primary_key=True, default=0, server_default="0")
    bod_market_value = Column(ExactNumeric(18, 10), nullable=False)
    bod_cashflow = Column(ExactNumeric(18, 10), nullable=False)
    eod_cashflow = Column(ExactNumeric(18, 10), nullable=False)
    eod_market_value = Column(ExactNumeric(18, 10), nullable=False)
    fees = Column(ExactNumeric(18, 10), nullable=False)
    calculation_lineage = Column(JSON(none_as_null=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_portfolio_timeseries_values_finite",
            "bod_market_value",
            "bod_cashflow",
            "eod_cashflow",
            "eod_market_value",
            "fees",
        ),
        Index(
            "ix_port_ts_norm_port_date_epoch",
            func.trim(portfolio_id),
            date.desc(),
            epoch.desc(),
        ),
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
    correlation_missing_reason = Column(String, nullable=True)
    alternate_lookup_key = Column(String, nullable=True)
    semantic_key = Column(String, nullable=True)
    payload_fingerprint = Column(String, nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("event_id", "service_name", name="_event_service_uc"),
        Index("ix_processed_events_alternate_lookup_key", "alternate_lookup_key"),
        Index(
            "uq_processed_events_service_semantic_key",
            "service_name",
            "semantic_key",
            unique=True,
            postgresql_where=semantic_key.isnot(None),
        ),
    )


def _default_outbox_partition_key(context) -> str:
    """Preserve aggregate-key dispatch for legacy direct ORM construction."""

    return str(context.get_current_parameters()["aggregate_id"])


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    aggregate_type = Column(String, nullable=False, index=True)
    aggregate_id = Column(String, nullable=False, index=True)
    partition_key = Column(String, nullable=False, default=_default_outbox_partition_key)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    topic = Column(String, nullable=False)
    status = Column(String, default="PENDING", nullable=False, index=True)
    correlation_id = Column(String, nullable=True)
    ingestion_job_id = Column(String, nullable=True)
    correlation_missing_reason = Column(String, nullable=True)
    alternate_lookup_key = Column(String, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    last_attempted_at = Column(DateTime(timezone=True), nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    claim_token = Column(String(64), nullable=True)
    claim_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_failure_reason_code = Column(String, nullable=True)
    last_failure_category = Column(String, nullable=True)
    last_failure_message = Column(String, nullable=True)
    last_failure_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index(
            "ix_outbox_events_status_created_at",
            "status",
            "created_at",
        ),
        Index(
            "ix_outbox_events_status_last_attempted_at",
            "status",
            "last_attempted_at",
        ),
        Index(
            "ix_outbox_events_status_next_attempt_created_at",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        Index(
            "ix_outbox_events_status_claim_next_attempt_created_at",
            "status",
            "claim_expires_at",
            "next_attempt_at",
            "created_at",
        ),
        Index(
            "ix_outbox_events_claim_token",
            "claim_token",
        ),
        Index(
            "ix_outbox_events_status_last_failure_at",
            "status",
            "last_failure_at",
        ),
        Index(
            "ix_outbox_events_stream_unresolved_order",
            "topic",
            "partition_key",
            "created_at",
            "id",
            postgresql_where=status.in_(("PENDING", "FAILED")),
        ),
        Index("ix_outbox_events_alternate_lookup_key", "alternate_lookup_key"),
    )


class OutboxRecoveryAudit(Base):
    __tablename__ = "outbox_recovery_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    outbox_id = Column(Integer, ForeignKey("outbox_events.id"), nullable=False, index=True)
    recovery_action = Column(String, nullable=False)
    requested_by = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    correlation_id = Column(String, nullable=True, index=True)
    prior_status = Column(String, nullable=False)
    new_status = Column(String, nullable=False)
    outcome = Column(String, nullable=False, index=True)
    outcome_message = Column(String, nullable=True)
    prior_retry_count = Column(Integer, nullable=False)
    prior_last_failure_reason_code = Column(String, nullable=True)
    prior_last_failure_category = Column(String, nullable=True)
    prior_last_failure_message = Column(String, nullable=True)
    prior_last_failure_at = Column(DateTime(timezone=True), nullable=True)
    requested_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ix_outbox_recovery_audit_outbox_requested_at",
            "outbox_id",
            "requested_at",
        ),
        Index(
            "ix_outbox_recovery_audit_outcome_requested_at",
            "outcome",
            "requested_at",
        ),
    )


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
    correlation_missing_reason = Column(String, nullable=True)
    alternate_lookup_key = Column(String, nullable=True)
    failure_reason = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    target_epoch = Column(Integer, nullable=False, default=0, server_default="0")
    source_revision = Column(Integer, nullable=False, default=1, server_default="1")
    lease_owner = Column(String(128), nullable=True)
    lease_token = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("portfolio_id", "aggregation_date", name="_portfolio_date_uc"),
        CheckConstraint(
            "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_token IS NOT NULL AND "
            "lease_expires_at IS NOT NULL)",
            name="ck_portfolio_aggregation_jobs_lease_complete",
        ),
        CheckConstraint(
            "target_epoch >= 0",
            name="ck_portfolio_aggregation_jobs_target_epoch_nonnegative",
        ),
        CheckConstraint(
            "source_revision >= 1",
            name="ck_portfolio_aggregation_jobs_source_revision_positive",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_status_aggregation_date",
            "status",
            "aggregation_date",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_status_updated_at",
            "status",
            "updated_at",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_status_lease_expiry",
            "status",
            "lease_expires_at",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_claim_order",
            "status",
            "portfolio_id",
            "aggregation_date",
            "id",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_portfolio_status_updated",
            "portfolio_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_portfolio_status_date_updated_id",
            "portfolio_id",
            "status",
            "aggregation_date",
            "updated_at",
            "id",
        ),
        Index(
            "ix_agg_jobs_port_corr_date_updated_id",
            "portfolio_id",
            "correlation_id",
            "aggregation_date",
            "updated_at",
            "id",
            postgresql_where=correlation_id.is_not(None),
        ),
        Index("ix_portfolio_aggregation_jobs_alternate_lookup_key", "alternate_lookup_key"),
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
    requeue_requested = Column(Boolean, nullable=False, default=False, server_default="false")
    source_correction_id = Column(String, nullable=True)
    correlation_id = Column(String, nullable=True)
    correlation_missing_reason = Column(String, nullable=True)
    alternate_lookup_key = Column(String, nullable=True)
    failure_reason = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    claimed_readiness_outbox_id = Column(BigInteger, nullable=False, default=0, server_default="0")
    valuation_lease_owner = Column(String(128), nullable=True)
    valuation_claim_token = Column(String(32), nullable=True)
    valuation_lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "valuation_claim_token IS NULL OR valuation_claim_token ~ '^[0-9a-f]{32}$'",
            name="ck_portfolio_valuation_jobs_claim_token",
        ),
        CheckConstraint(
            "(valuation_lease_owner IS NULL AND valuation_claim_token IS NULL "
            "AND valuation_lease_expires_at IS NULL) OR "
            "(valuation_lease_owner IS NOT NULL AND valuation_claim_token IS NOT NULL "
            "AND valuation_lease_expires_at IS NOT NULL)",
            name="ck_portfolio_valuation_jobs_lease_all_or_none",
        ),
        CheckConstraint(
            "valuation_lease_owner IS NULL OR btrim(valuation_lease_owner) <> ''",
            name="ck_portfolio_valuation_jobs_lease_owner_nonblank",
        ),
        CheckConstraint(
            "valuation_lease_expires_at IS NULL OR valuation_lease_expires_at "
            "NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_portfolio_valuation_jobs_lease_expiry_finite",
        ),
        CheckConstraint(
            "(status = 'PROCESSING' AND valuation_lease_owner IS NOT NULL "
            "AND valuation_claim_token IS NOT NULL AND valuation_lease_expires_at IS NOT NULL) "
            "OR (status <> 'PROCESSING' AND valuation_lease_owner IS NULL "
            "AND valuation_claim_token IS NULL AND valuation_lease_expires_at IS NULL)",
            name="ck_portfolio_valuation_jobs_processing_lease_state",
        ),
        UniqueConstraint(
            "portfolio_id",
            "security_id",
            "valuation_date",
            "epoch",
            name="_portfolio_security_valuation_date_epoch_uc",
        ),
        Index(
            "ix_portfolio_valuation_jobs_status_valuation_date",
            "status",
            "valuation_date",
        ),
        Index(
            "ix_portfolio_valuation_jobs_status_updated_at",
            "status",
            "updated_at",
        ),
        Index(
            "ix_portfolio_valuation_jobs_processing_lease_recovery",
            "valuation_lease_expires_at",
            "id",
            postgresql_where=status == "PROCESSING",
        ),
        Index(
            "ix_portfolio_valuation_jobs_claim_order_epoch",
            "status",
            "portfolio_id",
            "security_id",
            "valuation_date",
            epoch.desc(),
            "id",
        ),
        Index(
            "ix_portfolio_valuation_jobs_portfolio_status_updated",
            "portfolio_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_portfolio_valuation_jobs_portfolio_status_date_updated_id",
            "portfolio_id",
            "status",
            "valuation_date",
            "updated_at",
            "id",
        ),
        Index(
            "ix_val_jobs_norm_port_sec_date_epoch_status",
            func.trim(portfolio_id),
            func.trim(security_id),
            "valuation_date",
            "epoch",
            "status",
        ),
        Index(
            "ix_val_jobs_lineage_latest",
            "portfolio_id",
            func.trim(security_id),
            "epoch",
            valuation_date.desc(),
            id.desc(),
        ),
        Index(
            "ix_val_jobs_port_corr_date_updated_id",
            "portfolio_id",
            "correlation_id",
            "valuation_date",
            "updated_at",
            "id",
            postgresql_where=correlation_id.is_not(None),
        ),
        Index("ix_portfolio_valuation_jobs_alternate_lookup_key", "alternate_lookup_key"),
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
    failure_status_code = Column(Integer, nullable=True)
    failure_code = Column(String, nullable=True)
    failure_detail = Column(JSON(none_as_null=True), nullable=True)
    failure_headers = Column(JSON(none_as_null=True), nullable=True)
    # Fingerprint-only policy records require a database NULL, not JSON ``null``.
    # Keep this on the mapped type so every ingestion workflow receives the same
    # persistence semantics without adapter-specific coercion.
    request_payload = Column(JSON(none_as_null=True), nullable=True)
    request_payload_fingerprint = Column(String, nullable=True)
    request_payload_policy_version = Column(String(64), nullable=False)
    request_payload_classification = Column(String(32), nullable=False)
    request_payload_representation = Column(String(32), nullable=False)
    request_payload_replay_eligible = Column(Boolean, nullable=False)
    request_payload_partial_replay_eligible = Column(Boolean, nullable=False)
    request_payload_replay_expires_at = Column(DateTime(timezone=True), nullable=True)
    request_payload_retention_authority = Column(String(128), nullable=False)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_retried_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(failure_status_code IS NULL AND failure_code IS NULL "
            "AND failure_detail IS NULL AND failure_headers IS NULL) OR "
            "(failure_status_code IS NOT NULL "
            "AND failure_status_code BETWEEN 400 AND 599 "
            "AND failure_code IS NOT NULL "
            "AND failure_code = btrim(failure_code) "
            "AND failure_code <> '')",
            name="ck_ingestion_jobs_failure_outcome_complete",
        ),
        CheckConstraint(
            "request_payload_fingerprint IS NULL OR "
            "request_payload_fingerprint ~ "
            "'^hmac-sha256:v1:[A-Za-z0-9][A-Za-z0-9._-]{0,63}:[0-9a-f]{64}$'",
            name="ck_ingestion_jobs_payload_fingerprint_format",
        ),
        CheckConstraint(
            "request_payload_classification IN ('internal', 'confidential', 'restricted', "
            "'legacy_unclassified')",
            name="ck_ingestion_jobs_payload_classification",
        ),
        CheckConstraint(
            "request_payload_representation IN ('source_safe_replay', 'fingerprint_only', "
            "'legacy_redacted')",
            name="ck_ingestion_jobs_payload_representation",
        ),
        CheckConstraint(
            "request_payload_partial_replay_eligible = false OR "
            "request_payload_replay_eligible = true",
            name="ck_ingestion_jobs_payload_partial_replay",
        ),
        CheckConstraint(
            "(request_payload_replay_eligible = true "
            "AND request_payload_representation = 'source_safe_replay' "
            "AND request_payload IS NOT NULL "
            "AND request_payload_fingerprint IS NOT NULL "
            "AND request_payload_replay_expires_at IS NOT NULL) OR "
            "(request_payload_replay_eligible = false "
            "AND request_payload_replay_expires_at IS NULL)",
            name="ck_ingestion_jobs_payload_replay_authority",
        ),
        CheckConstraint(
            "request_payload_representation <> 'fingerprint_only' OR request_payload IS NULL",
            name="ck_ingestion_jobs_fingerprint_only_payload_absent",
        ),
        CheckConstraint(
            "request_payload_replay_expires_at IS NULL OR "
            "request_payload_replay_expires_at NOT IN "
            "('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_ingestion_jobs_payload_expiry_finite",
        ),
        CheckConstraint(
            "btrim(request_payload_policy_version) <> '' AND "
            "btrim(request_payload_retention_authority) <> ''",
            name="ck_ingestion_jobs_payload_policy_identity",
        ),
        Index("ix_ingestion_jobs_submitted_at", "submitted_at"),
        Index("ix_ingestion_jobs_status_submitted_at", "status", submitted_at.desc()),
        Index(
            "ix_ingestion_jobs_idempotency_key_submitted_at",
            "idempotency_key",
            submitted_at.desc(),
        ),
        Index(
            "ix_ingestion_jobs_idempotency_payload_fingerprint",
            "idempotency_key",
            "request_payload_fingerprint",
        ),
        Index(
            "ix_ingestion_jobs_submitted_completed_at",
            "submitted_at",
            "completed_at",
        ),
        Index(
            "ix_ingestion_jobs_correlation_status_id",
            "correlation_id",
            "status",
            id.desc(),
        ),
    )


class IngestionJobFailure(Base):
    __tablename__ = "ingestion_job_failures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    failure_id = Column(String, unique=True, index=True, nullable=False)
    job_id = Column(String, ForeignKey("ingestion_jobs.job_id"), index=True, nullable=False)
    failure_phase = Column(String, nullable=False)
    failure_reason = Column(Text, nullable=False)
    failed_record_keys = Column(JSON, nullable=True)
    failed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_ingestion_job_failures_job_failed_at", "job_id", failed_at.desc()),)


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
    error_reason_code = Column(
        String, index=True, nullable=False, server_default="UNCLASSIFIED_PROCESSING_ERROR"
    )
    error_reason = Column(Text, nullable=False)
    correlation_id = Column(String, nullable=True)
    ingestion_job_id = Column(
        String,
        ForeignKey("ingestion_jobs.job_id"),
        nullable=True,
    )
    correlation_missing_reason = Column(String, nullable=True)
    alternate_lookup_key = Column(String, nullable=True)
    payload_excerpt = Column(Text, nullable=True)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "ix_consumer_dlq_events_group_topic_observed_at",
            "consumer_group",
            "original_topic",
            observed_at.desc(),
        ),
        Index("ix_consumer_dlq_events_alternate_lookup_key", "alternate_lookup_key"),
        Index(
            "ix_consumer_dlq_events_job_observed_id",
            "ingestion_job_id",
            observed_at.desc(),
            id.desc(),
        ),
    )


class ConsumerDlqReplayAudit(Base):
    __tablename__ = "consumer_dlq_replay_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    replay_id = Column(String, unique=True, index=True, nullable=False)
    recovery_path = Column(String, nullable=False, server_default="consumer_dlq_replay", index=True)
    event_id = Column(String, index=True, nullable=False)
    replay_fingerprint = Column(String, index=True, nullable=False)
    correlation_id = Column(String, nullable=True)
    correlation_missing_reason = Column(String, nullable=True)
    alternate_lookup_key = Column(String, nullable=True)
    job_id = Column(String, nullable=True, index=True)
    endpoint = Column(String, nullable=True)
    replay_status = Column(String, nullable=False, index=True)
    dry_run = Column(Boolean, nullable=False, server_default="f")
    replay_reason = Column(Text, nullable=False)
    requested_by = Column(String, nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ix_consumer_dlq_replay_audit_path_status_requested_at",
            "recovery_path",
            "replay_status",
            requested_at.desc(),
        ),
        Index(
            "ix_consumer_dlq_replay_audit_fingerprint_status_path",
            "replay_fingerprint",
            "replay_status",
            "recovery_path",
            requested_at.desc(),
        ),
        Index("ix_consumer_dlq_replay_audit_alternate_lookup_key", "alternate_lookup_key"),
        Index(
            "ix_consumer_dlq_replay_audit_job_requested_id",
            "job_id",
            requested_at.desc(),
            id.desc(),
        ),
    )


class EnterpriseSecurityAuditEvent(Base):
    """Append-only, source-safe enterprise HTTP access-decision evidence."""

    __tablename__ = "enterprise_security_audit_events"

    event_id = Column(String(36), primary_key=True, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    component = Column(String(64), nullable=False)
    route_template = Column(String(256), nullable=False)
    method = Column(String(8), nullable=False)
    decision = Column(String(8), nullable=False)
    reason = Column(String(64), nullable=False)
    required_capability = Column(String(128), nullable=True)
    service_identity = Column(String(128), nullable=True)
    actor_id = Column(String(128), nullable=True)
    tenant_id = Column(String(128), nullable=True)
    role = Column(String(128), nullable=True)
    identity_posture = Column(String(16), nullable=False)
    correlation_id = Column(String(128), nullable=True)
    trace_id = Column(String(128), nullable=True)
    policy_version = Column(String(64), nullable=False)
    schema_version = Column(String(16), nullable=False, server_default="1.0")
    classification = Column(
        String(64),
        nullable=False,
        server_default="operational_security_audit",
    )

    __table_args__ = (
        CheckConstraint(
            "component IN ('ingestion_service', 'query_service', "
            "'query_control_plane_service', 'financial_reconciliation_service', "
            "'event_replay_service')",
            name="ck_enterprise_security_audit_component",
        ),
        CheckConstraint(
            "method IN ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE')",
            name="ck_enterprise_security_audit_method",
        ),
        CheckConstraint(
            "decision IN ('ALLOW', 'DENY')",
            name="ck_enterprise_security_audit_decision",
        ),
        CheckConstraint(
            "reason IN ('authorized', 'authorization_policy_denied', 'payload_too_large')",
            name="ck_enterprise_security_audit_reason",
        ),
        CheckConstraint(
            "identity_posture IN ('verified', 'unverified')",
            name="ck_enterprise_security_audit_identity_posture",
        ),
        CheckConstraint(
            "(identity_posture = 'verified' AND service_identity IS NOT NULL "
            "AND actor_id IS NOT NULL AND tenant_id IS NOT NULL AND role IS NOT NULL) OR "
            "(identity_posture = 'unverified' AND service_identity IS NULL "
            "AND actor_id IS NULL AND tenant_id IS NULL AND role IS NULL)",
            name="ck_enterprise_security_audit_identity_authority",
        ),
        CheckConstraint(
            "route_template LIKE '/%' AND route_template NOT LIKE '%?%' "
            "AND route_template NOT LIKE '%#%' AND route_template NOT LIKE '%://%'",
            name="ck_enterprise_security_audit_route_template",
        ),
        CheckConstraint(
            "schema_version = '1.0'",
            name="ck_enterprise_security_audit_schema_version",
        ),
        CheckConstraint(
            "classification = 'operational_security_audit'",
            name="ck_enterprise_security_audit_classification",
        ),
        Index(
            "ix_enterprise_security_audit_tenant_time_event",
            "tenant_id",
            occurred_at.desc(),
            event_id.desc(),
        ),
        Index(
            "ix_enterprise_security_audit_tenant_filter_time_event",
            "tenant_id",
            "component",
            "decision",
            occurred_at.desc(),
            event_id.desc(),
        ),
    )


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

    __table_args__ = (
        Index(
            "ix_position_state_status_watermark_updated",
            "status",
            "watermark_date",
            "updated_at",
        ),
        Index(
            "ix_position_state_watermark_updated",
            "watermark_date",
            "updated_at",
        ),
        Index(
            "ix_position_state_updated_watermark_key",
            "updated_at",
            "watermark_date",
            "portfolio_id",
            "security_id",
        ),
        Index(
            "ix_position_state_status_updated_watermark_key",
            "status",
            "updated_at",
            "watermark_date",
            "portfolio_id",
            "security_id",
        ),
        Index(
            "ix_position_state_port_norm_sec_epoch",
            "portfolio_id",
            func.trim(security_id),
            "epoch",
        ),
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
    correlation_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_instrument_reprocessing_state_impact_updated_security",
            "earliest_impacted_date",
            "updated_at",
            "security_id",
        ),
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
    correlation_id = Column(String, nullable=True)
    correlation_missing_reason = Column(String, nullable=True)
    alternate_lookup_key = Column(String, nullable=True)

    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_attempted_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)
    lease_owner = Column(String(128), nullable=True)
    lease_token = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_reprocessing_jobs_pending_reset_watermarks_security",
            text("(payload->>'security_id')"),
            unique=True,
            postgresql_where=text("job_type = 'RESET_WATERMARKS' AND status = 'PENDING'"),
        ),
        Index(
            "uq_reproc_jobs_pending_fx_pair",
            text("(payload->>'from_currency')"),
            text("(payload->>'to_currency')"),
            unique=True,
            postgresql_where=text("job_type = 'RESET_FX_WATERMARKS' AND status = 'PENDING'"),
        ),
        Index(
            "ix_reproc_jobs_pending_fx_priority",
            text("(payload->>'earliest_impacted_date')"),
            "created_at",
            "id",
            postgresql_where=text("job_type = 'RESET_FX_WATERMARKS' AND status = 'PENDING'"),
        ),
        Index(
            "ix_reprocessing_jobs_pending_resetwatermarks_priority",
            text("(payload->>'earliest_impacted_date')"),
            "created_at",
            "id",
            postgresql_where=text("job_type = 'RESET_WATERMARKS' AND status = 'PENDING'"),
        ),
        Index(
            "ix_reprocessing_jobs_job_type_status_created_at_id",
            "job_type",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_reprocessing_jobs_status_updated_at",
            "status",
            "updated_at",
        ),
        Index(
            "ix_reprocessing_jobs_processing_lease_recovery",
            "lease_expires_at",
            "id",
            postgresql_where=text("status = 'PROCESSING'"),
        ),
        Index(
            "ix_reproc_resetwm_sec_status_created_id",
            text("trim(payload->>'security_id')"),
            "status",
            "created_at",
            "id",
            postgresql_where=text("job_type = 'RESET_WATERMARKS'"),
        ),
        Index(
            "ix_reproc_resetwm_corr_status_created_id",
            "correlation_id",
            "status",
            "created_at",
            "id",
            postgresql_where=text("job_type = 'RESET_WATERMARKS'"),
        ),
        Index("ix_reprocessing_jobs_alternate_lookup_key", "alternate_lookup_key"),
        CheckConstraint(
            "(status = 'PROCESSING' AND lease_owner IS NOT NULL "
            "AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status <> 'PROCESSING' AND lease_owner IS NULL "
            "AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_reprocessing_jobs_processing_lease",
        ),
        CheckConstraint(
            "lease_owner IS NULL OR (lease_owner = btrim(lease_owner) AND lease_owner <> '')",
            name="ck_reprocessing_jobs_lease_owner_normalized",
        ),
        CheckConstraint(
            "lease_token IS NULL OR lease_token ~ '^[0-9a-f]{32}$'",
            name="ck_reprocessing_jobs_lease_token",
        ),
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

    __table_args__ = (
        Index(
            "ix_analytics_export_jobs_portfolio_status_created_at",
            "portfolio_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_analytics_export_jobs_status_updated_at",
            "status",
            "updated_at",
        ),
        Index(
            "ix_analytics_export_jobs_dataset_fingerprint_id",
            "dataset_type",
            "request_fingerprint",
            id.desc(),
        ),
    )


class PipelineStageState(Base):
    """
    Durable state tracker for orchestrated stage gates.
    Stage-1 scope tracks transaction-level readiness across independent processors.
    """

    __tablename__ = "pipeline_stage_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stage_name = Column(String, nullable=False, index=True)
    transaction_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, nullable=False, index=True)
    security_id = Column(String, nullable=True, index=True)
    business_date = Column(Date, nullable=False, index=True)
    epoch = Column(Integer, nullable=False, default=0, server_default="0", index=True)
    aggregation_revision = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String, nullable=False, default="PENDING", server_default="PENDING", index=True)
    cost_event_seen = Column(Boolean, nullable=False, default=False, server_default="f")
    cashflow_event_seen = Column(Boolean, nullable=False, default=False, server_default="f")
    ready_emitted_at = Column(DateTime(timezone=True), nullable=True)
    last_source_event_type = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "stage_name",
            "transaction_id",
            "epoch",
            name="_pipeline_stage_state_stage_tx_epoch_uc",
        ),
        CheckConstraint(
            "aggregation_revision >= 0",
            name="ck_pipeline_stage_aggregation_revision_nonnegative",
        ),
        Index(
            "ix_pipeline_stage_state_portfolio_date_stage_status",
            "portfolio_id",
            "business_date",
            "stage_name",
            "status",
        ),
        Index(
            "ix_pipeline_stage_state_port_status_date_stage_epoch_updated_id",
            "portfolio_id",
            "status",
            business_date.desc(),
            "stage_name",
            epoch.desc(),
            updated_at.desc(),
            id.asc(),
        ),
        Index(
            "ix_pipeline_stage_state_port_stage_date_epoch_id",
            "portfolio_id",
            "stage_name",
            business_date.desc(),
            epoch.desc(),
            id.desc(),
        ),
    )


class FinancialReconciliationRun(Base):
    """
    Durable execution record for independent financial controls.
    """

    __tablename__ = "financial_reconciliation_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, unique=True, index=True, nullable=False)
    reconciliation_type = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, nullable=True, index=True)
    business_date = Column(Date, nullable=True, index=True)
    epoch = Column(Integer, nullable=True, index=True)
    aggregation_revision = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="RUNNING", server_default="RUNNING", index=True)
    requested_by = Column(String, nullable=True)
    dedupe_key = Column(String, nullable=True, unique=True, index=True)
    correlation_id = Column(String, nullable=True)
    tolerance = Column(ExactNumeric(18, 10), nullable=True)
    summary = Column(JSON, nullable=True)
    failure_reason = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        _finite_numeric_check_constraint(
            "ck_fin_recon_tolerance_finite",
            "tolerance",
        ),
        CheckConstraint(
            "tolerance >= 0",
            name="ck_fin_recon_tolerance_nonnegative",
        ),
        CheckConstraint(
            "aggregation_revision IS NULL OR aggregation_revision >= 0",
            name="ck_fin_recon_aggregation_revision_nonnegative",
        ),
        Index(
            "ix_fin_recon_scope_revision_type",
            "portfolio_id",
            "business_date",
            "epoch",
            "aggregation_revision",
            "reconciliation_type",
        ),
        Index(
            "ix_financial_reconciliation_runs_type_status_started_at",
            "reconciliation_type",
            "status",
            started_at.desc(),
        ),
        Index(
            "ix_financial_reconciliation_runs_port_status_started_id",
            "portfolio_id",
            "status",
            started_at.desc(),
            id.asc(),
        ),
        Index(
            "ix_financial_reconciliation_runs_port_type_started_id",
            "portfolio_id",
            "reconciliation_type",
            started_at.desc(),
            id.desc(),
        ),
        Index(
            "ix_fin_recon_runs_port_corr_started_id",
            "portfolio_id",
            "correlation_id",
            started_at.desc(),
            id.asc(),
        ),
        Index(
            "ix_fin_recon_runs_port_req_by_started_id",
            "portfolio_id",
            "requested_by",
            started_at.desc(),
            id.asc(),
        ),
        Index(
            "ix_fin_recon_runs_port_date_epoch_started_id",
            "portfolio_id",
            "business_date",
            "epoch",
            started_at.desc(),
            id.desc(),
        ),
    )


class FinancialReconciliationFinding(Base):
    """
    Durable finding rows emitted by financial reconciliation runs.
    """

    __tablename__ = "financial_reconciliation_findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    finding_id = Column(String, unique=True, index=True, nullable=False)
    run_id = Column(
        String,
        ForeignKey("financial_reconciliation_runs.run_id"),
        nullable=False,
        index=True,
    )
    reconciliation_type = Column(String, nullable=False, index=True)
    finding_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, nullable=True, index=True)
    security_id = Column(String, nullable=True, index=True)
    transaction_id = Column(String, nullable=True, index=True)
    business_date = Column(Date, nullable=True, index=True)
    epoch = Column(Integer, nullable=True, index=True)
    expected_value = Column(JSON, nullable=True)
    observed_value = Column(JSON, nullable=True)
    detail = Column(JSON, nullable=True)
    owner = Column(String(100), nullable=False)
    resolution_state = Column(
        String(20),
        nullable=False,
        default="OPEN",
        server_default="OPEN",
        index=True,
    )
    resolution_actor = Column(String(200), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    tolerance = Column(ExactNumeric(18, 10), nullable=True)
    observed_delta = Column(ExactNumeric(18, 10), nullable=True)
    repair_recommendation = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "btrim(owner) <> ''",
            name="ck_fin_recon_finding_owner_nonempty",
        ),
        CheckConstraint(
            "resolution_state IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'WAIVED', 'SUPPRESSED')",
            name="ck_fin_recon_finding_resolution_state",
        ),
        CheckConstraint(
            "("
            "resolution_state IN ('OPEN', 'IN_PROGRESS') "
            "AND resolution_actor IS NULL AND resolved_at IS NULL"
            ") OR ("
            "resolution_state IN ('RESOLVED', 'WAIVED', 'SUPPRESSED') "
            "AND resolution_actor IS NOT NULL AND btrim(resolution_actor) <> '' "
            "AND resolved_at IS NOT NULL AND resolved_at >= created_at"
            ")",
            name="ck_fin_recon_finding_resolution_evidence",
        ),
        _finite_numeric_check_constraint(
            "ck_fin_recon_finding_tolerance_finite",
            "tolerance",
        ),
        CheckConstraint(
            "tolerance >= 0",
            name="ck_fin_recon_finding_tolerance_nonnegative",
        ),
        _finite_numeric_check_constraint(
            "ck_fin_recon_finding_observed_delta_finite",
            "observed_delta",
        ),
        CheckConstraint(
            "btrim(repair_recommendation) <> ''",
            name="ck_fin_recon_finding_repair_nonempty",
        ),
        Index(
            "ix_financial_reconciliation_findings_run_severity_type_id",
            "run_id",
            "severity",
            "finding_type",
            id.asc(),
        ),
        Index(
            "ix_financial_reconciliation_findings_run_severity_created_id",
            "run_id",
            "severity",
            created_at.desc(),
            id.desc(),
        ),
        Index(
            "ix_fin_recon_findings_run_resolution_severity_created_id",
            "run_id",
            "resolution_state",
            "severity",
            created_at.asc(),
            id.asc(),
        ),
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
