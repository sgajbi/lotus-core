# CR-1341 Image Provenance Parity Hardening

## Scope

Follow-up hardening for the image provenance and release manifest contract introduced in CR-1337
and tightened in CR-1339.

## Objective

Make image release evidence stricter and easier to compare across OCI labels, release manifests,
and runtime `/version` responses. The goal is to reduce release-review ambiguity for the governed
image requirements: full Git SHA tagging, branch/build/repo/pipeline metadata, digest capture,
SBOM, vulnerability scan, signing, provenance attestation, digest deployment, same-image
promotion, and no build-secret leakage.

## Changes

1. Added an explicit OCI label map to `portfolio_common.build_metadata.BuildMetadataResponse`.
2. Updated the standard `/version` OpenAPI example to include the OCI label map.
3. Added `oci_labels` to image release manifests so release evidence can be compared directly
   with runtime metadata and OCI label names.
4. Tightened `scripts/write_image_release_manifest.py` to require a full 40-character lowercase
   Git SHA, non-placeholder branch/build/repo/pipeline metadata, a valid `sha256:` digest, and
   promotion evidence across `dev`, `uat`, and `prod`.
5. Extended `scripts/image_provenance_guard.py` and focused tests so future changes cannot drop
   `/version` OCI-label parity or release-manifest OCI-label evidence silently.
6. Updated README, operations docs, wiki source, and repository context to match the stricter
   implementation-backed contract.

## Behavior And Compatibility

`GET /version` adds the `oci_labels` field. Existing metadata fields remain unchanged, so this is a
backward-compatible operator endpoint extension. No business route path, request DTO, business
response DTO, database schema, Kafka contract, metric name, Dockerfile, workflow trigger, or
runtime topology changed.

The release manifest writer now rejects short pseudo-SHAs, placeholder release identity, partial
promotion environments, and malformed digests instead of producing misleading release evidence.

Local builds may still report `LOTUS_IMAGE_DIGEST=unknown`: a final registry digest cannot be known
before the build/push resolves it. Release manifests and deployment/runtime metadata carry the
resolved digest for release and operator parity.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/scripts/test_write_image_release_manifest.py tests/unit/scripts/test_image_provenance_guard.py tests/unit/scripts/test_prebuild_ci_images.py -q`
2. `python scripts/image_provenance_guard.py`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/build_metadata.py src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py scripts/write_image_release_manifest.py scripts/image_provenance_guard.py tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/scripts/test_write_image_release_manifest.py tests/unit/scripts/test_image_provenance_guard.py --ignore E501,I001`
4. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/build_metadata.py src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py scripts/write_image_release_manifest.py scripts/image_provenance_guard.py tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/scripts/test_write_image_release_manifest.py tests/unit/scripts/test_image_provenance_guard.py`

## Documentation, Wiki, Context, And Skill Decision

Updated README, `docs/operations-runbook.md`, wiki Operations Runbook source, repository context,
and the codebase review ledger because operator-visible `/version` metadata and release evidence
truth changed.

No platform skill source change is required. The reusable lesson is already captured in
`lotus-ci-enforcement-governance` and now enforced locally through `make image-provenance-guard`,
manifest writer assertions, and focused pass/fail tests.

Wiki source changed and must be published after merge to `main`.

## Remaining Work

PR CI should prove `make architecture-guard`, `make quality-wiki-docs-gate`, and the first real
GitHub image release workflow run after merge should validate GHCR permissions, Trivy availability,
Cosign signing, and BuildKit SBOM/provenance attachment against the hosted runner environment.
