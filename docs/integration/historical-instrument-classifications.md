# Historical instrument classifications

`InstrumentReferenceBundle:v1` retains source-provided security-to-group assignments through
the existing classification reference routes. The effective label dictionary and current
instrument enrichment remain separate views. A current sector label is never evidence of a
historical assignment.

## Write and select

Submit `assignment_cut` to `POST /ingest/reference/classification-taxonomy` with the existing
`ingestion.reference_data.write` capability. Supply exactly one mode: legacy
`classification_taxonomy` rows or one assignment cut. The cut declares producer, classification
set, source record/version, taxonomy revision, dimension, business coverage, source observation
and generation times, the complete expected security/group universe, and effective assignments.
Every assignment carries its own source record and observation time.

Intervals are half-open: `effective_from` and `coverage_from` are inclusive; `effective_to` and
`coverage_to` are exclusive. Conflicting intervals for the same security, unknown declared
groups/securities, duplicate universe identities, and invalid source time order are rejected.
Adjacent intervals allow a genuine reclassification. Missing security coverage is retained as
partial evidence, never filled from current instrument labels.

The source cut is bounded to 500 securities, 128 groups, 2,000 assignments and 512 KiB of
canonical UTF-8 content. The content hash covers the entire validated source command, including
provenance, expected universe, times and correction relationship. Universe/assignment ordering
does not affect identity. Core derives `content_hash` using SHA-256 over canonical JSON and
`cut_id` using SHA-256 over `instrument-classification-cut-v1:` followed by that content hash.
Both pins include the `sha256:` prefix. These are custody identities, not supplier signatures.

Select history using `history_selection` on
`POST /integration/reference/classification-taxonomy` with the existing
`source_data.instrument_reference_bundle.read` capability. Send the exact producer, set, source
record/version, cut/content pins and expected universe, plus `period_start`, inclusive
`period_end`, `source_as_of` and `known_at`. Top-level `as_of_date` must equal `period_end`;
`taxonomy_scope`, when supplied, must be `instrument`. Unknown/mismatched pins and declared
universe mismatches return `history.status=UNAVAILABLE`, without assignments or retained content.
`source_as_of` independently limits source observation; `known_at` independently limits Core
receipt. Neither cutoff replaces the requested business interval.

Responses put assignment evidence in `history`, with legacy `records=[]`. `COMPLETE` means only
uninterrupted coverage of every security in the caller's exact source-declared universe over the
requested interval. `PARTIAL` lists `missing_security_ids` and bounded reason codes. Rows retain
their original intervals rather than being rewritten to the selected interval. Invalid retained
custody is unavailable. Every history response keeps `qualification=RETAINED_UNQUALIFIED`,
`compatibility=UNAVAILABLE`, `source_evidence_current=false`, and freshness unavailable.
The shared degradation summary remains UNAVAILABLE for unqualified producer and unproven joined
compatibility, even when declared assignment coverage is complete. These are different claims.

## Corrections and custody

Version 1 has no predecessor. A correction must supply the exact latest `predecessor_cut_id`
and the next contiguous source version within producer/set/source-record scope. Reusing a
version with identical canonical content replays the original receipt; changed content returns
`409 CLASSIFICATION_HISTORY_CONFLICT`. Concurrent source submissions serialize within that
scope. A correction never updates or deletes its predecessor; original A and correction B remain
separately selectable by their exact pins. PostgreSQL refuses updates, deletes and populated
truncation. Downgrade is supported only while the new table is empty; populated custody requires
an explicit retention decision outside this migration.
Empty truncation and downgrade require READ COMMITTED isolation, which can establish a fresh
emptiness check after locking. Repeatable historical snapshots cannot authorize teardown. The
downgrade takes an exclusive table lock with a five-second lock timeout before checking rows.

The ingestion receipt follows the existing reference command/job lifecycle. The append commits
before queued bookkeeping; a bookkeeping failure does not erase a retained cut. Retrying the
same canonical cut can recover its existing custody through the reference flow. This slice does
not claim a new atomic transaction encompassing reference retention and job bookkeeping.

## Controlled example and validation

The synthetic fixture in `tests/test_support/classification_history.py` declares securities
`SYNTHETIC_A`/`SYNTHETIC_B`, January coverage, and groups `TECHNOLOGY`/`FINANCE`. The registered
HTTP PostgreSQL test submits original A and a correction B moving A to FINANCE on January 16,
then selects both original and corrected versions. It also exercises missing securities,
foreign/unknown pins, mismatched universes and independent source/Core time cutoffs. The same
suite proves concurrent replay, database immutability and actual empty/populated migration
behavior in an owned namespace. This is controlled software proof, not live-provider evidence.
The suite is registered in the existing `query-authority-db-contract` hosted lane. It also
proves refusal under repeatable snapshots and after a truncate waits for an admission to commit.

Run from the `lotus-core` repository root with repository dependencies installed:

PowerShell:

```powershell
python scripts/development/repository_python.py -m pytest tests/unit/services/query_control_plane_service/application/test_classification_history.py -q -W error
$env:LOTUS_TEST_SCOPE = 'integration-lite'
$env:LOTUS_TEST_ENV_PROFILE = 'integration'
python scripts/development/repository_python.py -m pytest tests/integration/services/query_control_plane_service/test_classification_history_postgresql.py -q -W error
```

Bash:

```bash
python scripts/development/repository_python.py -m pytest tests/unit/services/query_control_plane_service/application/test_classification_history.py -q -W error
LOTUS_TEST_SCOPE=integration-lite LOTUS_TEST_ENV_PROFILE=integration python scripts/development/repository_python.py -m pytest tests/integration/services/query_control_plane_service/test_classification_history_postgresql.py -q -W error
```

The native test harness provisions its own PostgreSQL/migration stack and verifies cleanup
ownership. Do not point it at a foreign or production database. Use the native validated local
image workflow when prerequisite images need building; source contracts alone do not prove
container packaging or deployment behavior.

## Ownership boundary

This is a bounded child of existing reference custody inside the existing deployables, with
shared typed contracts, a pure identity/coverage domain module, and the existing ingestion/read
ports. No runtime split is justified. PostgreSQL retention and query selection do not certify
the supplier, taxonomy entitlement, bank-complete source universe, compatible valuation/FX or
benchmark cuts, financial pooled group returns, BF purpose approval, or maker/checker policy.
Manage owns membership; Performance owns attribution and benchmark mathematics. Existing
analytics export custody remains the owner of retained downstream exports and corrections.
