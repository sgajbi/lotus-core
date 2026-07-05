"""Governed active/current predicates for source-data lifecycle records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

ACTIVE_STATUS = "active"
DISCRETIONARY_MANDATE_TYPE = "discretionary"


@dataclass(frozen=True)
class SourceLifecyclePredicate:
    """Named source-data active/current predicate shared by indexes and reads."""

    concept: str
    status_column: str
    description: str
    active_status: str = ACTIVE_STATUS
    required_sql_predicates: tuple[str, ...] = ()

    @property
    def sql(self) -> str:
        predicates = [
            *self.required_sql_predicates,
            f"{self.status_column} = '{self.active_status}'",
        ]
        return " AND ".join(predicates)

    def sqlalchemy_filter(self, status_column: Any):
        return status_column == self.active_status

    def postgresql_where(self):
        return text(self.sql)


DPM_DISCRETIONARY_MANDATE_ACTIVE = SourceLifecyclePredicate(
    concept="DPM discretionary mandate binding active authority",
    status_column="discretionary_authority_status",
    required_sql_predicates=(f"mandate_type = '{DISCRETIONARY_MANDATE_TYPE}'",),
    description=(
        "A portfolio mandate binding is active/current for DPM source reads when the mandate "
        "type is discretionary, the discretionary authority status is active, and the effective "
        "window includes the requested as-of date."
    ),
)

CLIENT_RESTRICTION_ACTIVE = SourceLifecyclePredicate(
    concept="Client restriction profile active",
    status_column="restriction_status",
    description=(
        "A client restriction profile is active/current when restriction_status is active and "
        "the effective window includes the requested as-of date."
    ),
)

SUSTAINABILITY_PREFERENCE_ACTIVE = SourceLifecyclePredicate(
    concept="Sustainability preference profile active",
    status_column="preference_status",
    description=(
        "A sustainability preference profile is active/current when preference_status is active "
        "and the effective window includes the requested as-of date."
    ),
)

CLIENT_TAX_PROFILE_ACTIVE = SourceLifecyclePredicate(
    concept="Client tax profile active",
    status_column="profile_status",
    description=(
        "A client tax profile is active/current when profile_status is active and the effective "
        "window includes the requested as-of date."
    ),
)

CLIENT_TAX_RULE_SET_ACTIVE = SourceLifecyclePredicate(
    concept="Client tax rule set active",
    status_column="rule_status",
    description=(
        "A client tax rule set is active/current when rule_status is active and the effective "
        "window includes the requested as-of date."
    ),
)

CLIENT_INCOME_NEEDS_ACTIVE = SourceLifecyclePredicate(
    concept="Client income needs schedule active",
    status_column="need_status",
    description=(
        "A client income needs schedule is active/current when need_status is active and the "
        "schedule window includes the requested as-of date."
    ),
)

LIQUIDITY_RESERVE_ACTIVE = SourceLifecyclePredicate(
    concept="Liquidity reserve requirement active",
    status_column="reserve_status",
    description=(
        "A liquidity reserve requirement is active/current when reserve_status is active and the "
        "effective window includes the requested as-of date."
    ),
)

PLANNED_WITHDRAWAL_ACTIVE = SourceLifecyclePredicate(
    concept="Planned withdrawal schedule active",
    status_column="withdrawal_status",
    description=(
        "A planned withdrawal schedule is active/current when withdrawal_status is active and the "
        "scheduled date falls inside the requested projection window."
    ),
)

MODEL_PORTFOLIO_TARGET_ACTIVE = SourceLifecyclePredicate(
    concept="Model portfolio target active",
    status_column="target_status",
    description=(
        "A model portfolio target is active/current when target_status is active and the "
        "effective window includes the requested as-of date."
    ),
)

BENCHMARK_DEFINITION_ACTIVE = SourceLifecyclePredicate(
    concept="Benchmark definition active",
    status_column="benchmark_status",
    description=(
        "A benchmark definition is active/current when benchmark_status is active and the "
        "effective window includes the requested as-of date."
    ),
)

INDEX_DEFINITION_ACTIVE = SourceLifecyclePredicate(
    concept="Index definition active",
    status_column="index_status",
    description=(
        "An index definition is active/current when index_status is active and the effective "
        "window includes the requested as-of date."
    ),
)

ACTIVE_SOURCE_LIFECYCLE_PREDICATES = (
    DPM_DISCRETIONARY_MANDATE_ACTIVE,
    CLIENT_RESTRICTION_ACTIVE,
    SUSTAINABILITY_PREFERENCE_ACTIVE,
    CLIENT_TAX_PROFILE_ACTIVE,
    CLIENT_TAX_RULE_SET_ACTIVE,
    CLIENT_INCOME_NEEDS_ACTIVE,
    LIQUIDITY_RESERVE_ACTIVE,
    PLANNED_WITHDRAWAL_ACTIVE,
    MODEL_PORTFOLIO_TARGET_ACTIVE,
    BENCHMARK_DEFINITION_ACTIVE,
    INDEX_DEFINITION_ACTIVE,
)
