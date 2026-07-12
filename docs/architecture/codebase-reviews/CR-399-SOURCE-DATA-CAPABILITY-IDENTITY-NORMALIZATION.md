# CR-399: Source-Data Capability Identity Normalization

Date: 2026-05-28

## Scope

Shared `portfolio_common.source_data_security.required_source_data_capability(...)`.

## Finding

Source-data security profile lookup normalized product names before validation, but entitlement
capability generation derived the capability string from the raw caller input. A valid padded
product name such as ` portfolioAnalyticsReference ` could therefore pass validation while
producing a malformed capability containing non-canonical spacing.

## Change

Capability generation now resolves the governed security profile first and derives the capability
from the catalog-owned `profile.product_name`. Added direct shared-library coverage proving padded
mixed-case product input resolves to the canonical
`source_data.portfolio_analytics_reference.read` entitlement.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_security.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/source_data_security.py tests/unit/libs/portfolio-common/test_source_data_security.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a source-data
security and entitlement-governance correctness slice.
