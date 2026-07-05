from portfolio_common.source_lifecycle_predicates import (
    ACTIVE_SOURCE_LIFECYCLE_PREDICATES,
    ACTIVE_STATUS,
    CLIENT_RESTRICTION_ACTIVE,
    DISCRETIONARY_MANDATE_TYPE,
    DPM_DISCRETIONARY_MANDATE_ACTIVE,
)


def test_source_lifecycle_predicates_are_named_and_documented() -> None:
    concepts = [predicate.concept for predicate in ACTIVE_SOURCE_LIFECYCLE_PREDICATES]

    assert len(concepts) == len(set(concepts))
    assert {predicate.active_status for predicate in ACTIVE_SOURCE_LIFECYCLE_PREDICATES} == {
        ACTIVE_STATUS
    }
    assert all(predicate.status_column for predicate in ACTIVE_SOURCE_LIFECYCLE_PREDICATES)
    assert all(
        "active/current" in predicate.description
        for predicate in ACTIVE_SOURCE_LIFECYCLE_PREDICATES
    )


def test_source_lifecycle_predicates_publish_reviewable_partial_index_sql() -> None:
    assert (
        DPM_DISCRETIONARY_MANDATE_ACTIVE.sql == f"mandate_type = '{DISCRETIONARY_MANDATE_TYPE}' "
        f"AND discretionary_authority_status = '{ACTIVE_STATUS}'"
    )
    assert CLIENT_RESTRICTION_ACTIVE.sql == f"restriction_status = '{ACTIVE_STATUS}'"
    assert str(CLIENT_RESTRICTION_ACTIVE.postgresql_where()) == CLIENT_RESTRICTION_ACTIVE.sql
