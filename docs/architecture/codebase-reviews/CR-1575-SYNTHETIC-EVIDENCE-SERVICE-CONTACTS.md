# CR-1575: Synthetic-Evidence Service Contacts

## Objective

Keep generated-evidence leakage checks strict for personal data while recognizing only explicitly
governed, non-routable service contact aliases.

## Finding

After the OpenAPI Spectral gate generated ignored artifacts under `output/openapi`, the synthetic
fixture leakage guard classified `support.ops@lotus.local` as a personal email address. The source
value is a documented service alias on the non-routable `.local` namespace, but the guard applied a
generic email regex without consulting structured policy.

This made validation order affect results: lint passed before OpenAPI generation and failed after
it, even though the same commit and source files were under test.

## Change

1. Added `leakage_guard.allowed_service_emails` to the existing structured synthetic-data standard.
2. Allowed only exact case-insensitive values from that list during evidence scanning.
3. Required each allowed value to be a syntactically valid `.local` address and rejected external
   addresses, duplicates, malformed values, and missing list structure.
4. Added tests proving the governed alias passes while a near-match service alias and a personal
   address remain findings.
5. Kept generated output in scope; no file deletion, path exclusion, broad domain wildcard, or
   regex weakening hides evidence.

## Validation

- focused leakage-guard tests: `8 passed`;
- `make synthetic-fixture-leakage-guard` passed with generated OpenAPI artifacts present;
- focused Ruff lint and format checks passed; and
- full lint is rerun after this commit to prove validation-order independence.

## Compatibility

No API artifact, contact value, route, example, event, database, runtime, or downstream contract
changed. The standard now expresses the intended distinction between personal email evidence and a
non-routable support service identity.

## Documentation Decision

The synthetic-data standard, review ledger, and this review changed. README, repository context,
API governance guidance, OpenAPI source, supported features, migrations, and wiki source require no
change because product/API behavior and operator guidance did not change.
