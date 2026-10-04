# Client restriction profile authority

`POST /integration/portfolios/{portfolio_id}/client-restriction-profile` serves
`ClientRestrictionProfile:v1` from effective mandate and restriction evidence. Core owns source
selection; Manage owns construction decisions based on the qualified response.

## Effective revision selection

Core first selects restrictions effective on `as_of_date` for the resolved portfolio/client and
the requested mandate or global mandate scope. It ranks each `(restriction_scope,
restriction_code)` by effective start, observation time, version, update/create time and row ID.
Only then does the default active-only view filter the selected revision's lifecycle status.
A later inactive or suspended revision therefore cannot reveal its older active predecessor.
`include_inactive_restrictions=true` returns the selected effective revision with its status,
version and source-record lineage; it is not a history listing. Future records are not eligible,
and effective end dates are inclusive.

No active records remains `INCOMPLETE` / `CLIENT_RESTRICTION_PROFILE_EMPTY`, with missing
`client_restrictions` evidence and `MISSING` data quality. Absence of qualified source evidence
does not establish an authoritative unrestricted client.

## Selector admission and retained legacy evidence

`POST /ingest/client-restriction-profiles` trims surrounding whitespace in all four selector
families. Every supplied element must be non-blank, including mixed valid/blank lists. Invalid
elements produce a useful field-level 422 before command dispatch. Scoped instrument, issuer,
country and asset-class records require at least one populated selector family. The existing
policy permits any family regardless of the declared scope; selectors are alternatives (OR),
not a requirement that every family or the declared family's particular list be populated.
Client and mandate scopes may intentionally have all four lists empty as global controls.

Historical malformed rows are retained. The reader preserves blank selector elements instead of
dropping them into an empty global rule. If any selected row has unusable selectors, the response
is `UNAVAILABLE` / `CLIENT_RESTRICTION_PROFILE_INVALID_SELECTORS`, with `INVALID` data quality
and missing `client_restrictions`. Entries retain version, status and source-record lineage for
diagnosis. Consumers must refuse this profile before matching or making construction decisions;
they must not use a malformed entry as an unrestricted or global active rule. Corrected source
evidence must arrive through normal versioned admission; history is not rewritten by the read.

## Validation boundary

The owning PostgreSQL regression exercises validated admission DTOs and actual reference-data
upserts, followed by committed reload and the registered QCP route. It covers lifecycle
supersession, corrections, historical/future dates, independent codes, supported selector
families, intentional global controls, client/mandate filters and retained malformed history.
Registered ingestion tests assert 422 and zero command dispatch for blank/mixed selectors.
These are synthetic source-product proofs, not live rebalancing or banking approval.

The optional product `tenant_id` remains lineage under the existing QCP restriction interface;
request-header admission does not by itself establish database tenant isolation for this family.
The remaining tenant-authority work is governed separately. This selector/lifecycle correction
does not extend that claim.
