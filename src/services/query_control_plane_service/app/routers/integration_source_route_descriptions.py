"""OpenAPI descriptions for tenant-scoped integration source products."""

PORTFOLIO_MANAGER_BOOK_DESCRIPTION = (
    "What: Return source-owned portfolio memberships for a portfolio-manager book.\n"
    "How: Select effective roles (or the bounded `advisor_id` fallback) in the admitted tenant; "
    "a supplied tenant assertion must match before I/O.\n"
    "When: Use for lotus-manage PM-book cohort discovery, not hierarchy, entitlement, or "
    "relationship-householding."
)

CIO_MODEL_CHANGE_COHORT_DESCRIPTION = (
    "What: Return source-owned affected discretionary mandates for an approved CIO model.\n"
    "How: Resolve the global approved model and effective bindings rooted in the admitted tenant; "
    "a supplied tenant assertion must match before I/O.\n"
    "When: Use for lotus-manage CIO_MODEL_CHANGE discovery, not tactical house-view or execution."
)

DPM_PORTFOLIO_UNIVERSE_DESCRIPTION = (
    "What: Return source-owned DPM universe candidates from effective discretionary bindings.\n"
    "How: Apply admitted-tenant, as-of, model, authority, and deterministic paging controls; a "
    "supplied tenant assertion must match before I/O.\n"
    "When: Use for lotus-manage discovery before campaigns, not suitability, ranking, or execution."
)
