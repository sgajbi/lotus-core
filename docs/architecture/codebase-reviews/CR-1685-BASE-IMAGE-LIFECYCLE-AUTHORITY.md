# CR-1685 Base-Image Lifecycle Authority

## Objective

Close the source-governance portion of #927 without changing the Core runtime stack: bind every
Core-built service image to one immutable, mature base-image identity and fail closed when its
runtime, distribution, target platform, package-support, ownership, or review evidence is absent,
stale, or unsupported.

## Decision

Core retains the widely deployed Docker Official `python:3.11-slim-bookworm` base already proven by
the application and runtime suites. The inventory records its immutable OCI index, exact
`linux/amd64` child manifest and config digests, Docker Official Images source revision, CPython
security-support phase, Debian Bookworm LTS posture, and exact-image Debian package-support check.

Core also retains the bounded raw OCI index and runtime-manifest bytes in
`contracts/security/base-image-manifest-evidence.v1.json`. The guard recomputes the parent and child
SHA-256 digests, selects exactly one `linux/amd64` descriptor, and derives the config identity from
the verified child document. Digest-shaped authored fields cannot independently authorize this
chain.

Availability in a multi-platform index is not treated as deployment support. The governed release
target is `linux/amd64`; historical index entries for other platforms do not authorize production
deployment. Python's upstream authority describes support through approximately October 2027, so
Core records `2027-10-01` as the conservative machine-readable authority boundary and uses the same
local fail-closed cutoff instead of fabricating a later precise upstream end date. The gate requires
every local cutoff to be no later than its authority boundary. Evidence is reviewed at most every
30 days and immediately when the base digest,
permitted platform, official-image membership, or upstream lifecycle changes.

## Enforcement

`make base-image-lifecycle-guard`, also invoked by `make image-provenance-guard`, verifies:

- all ten Core service Dockerfiles use the governed immutable base identity;
- the `linux/amd64` child/config digest and attached-metadata distinction are explicit;
- retained registry bytes hash to the governed parent/child identities and bind descriptor media
  type, size, platform, child reference, and config digest; Docker reference parsing independently
  derives the image registry/repository, which must match both the lifecycle fields and the
  governed registry API authority, so authored metadata cannot reattribute another registry's
  bytes; the approved identity is specifically Docker Official Images `library/python` with the
  governed `3.11-slim-bookworm` tag and source revision, not any self-consistent Docker Hub image;
- CPython and Debian authorities remain current, each local cutoff is bounded by its upstream
  authority end date, and the earliest local cutoff owns release posture;
- Docker Official Images source/registry authority is complete, credential-free HTTPS evidence and
  its non-empty verification command binds the exact governed image;
- the exact image has a clean `debian-security-support` result;
- ownership, remediation issue, observed date, and bounded next review are present; and
- third-party Compose images are explicitly outside the Core-built release boundary, not silently
  presented as production-certified artifacts.

## Compatibility and documentation decision

This is build/release governance only. It adds no dependency, service, sidecar, datastore, API,
OpenAPI, event, database, migration, calculation, or topology change. Repository context, the
operator runbook, review ledger, and authored wiki are updated because release truth changed.
No API/OpenAPI, migration, supported-feature, or platform-context update is required.

## Validation

- focused lifecycle-guard unit tests cover current posture, deterministic replay, Dockerfile digest
  drift, missing inventory, stale evidence, EOL, experimental posture, unclassified Compose images,
  unresolved target child digest, missing package-support proof, incomplete/credentialed identity
  authority, wrong-image verification, and local cutoffs beyond upstream authority;
- scoped Ruff format/check;
- adversarial evidence tests cover missing/malformed registry evidence, changed parent or child
  bytes, missing platform selection, descriptor drift, config drift, credentialed authority, and
  unrelated or ungoverned registry authorities, image/lifecycle location mismatches, and
  self-consistent but unapproved Docker Hub repositories;
- direct `make base-image-lifecycle-guard` and `make image-provenance-guard`;
- online `update_base_image_manifest_evidence.py --check` against Docker Hub raw OCI bytes;
- exact-image `debian-security-support` execution on `linux/amd64` produced no ended or limited
  installed-package finding on 2026-08-12.
