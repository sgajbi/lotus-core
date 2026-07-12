# CR-1337 Image Provenance And Version Endpoint

## Scope

Runtime supply-chain provenance, immutable publication, and operator metadata for all `lotus-core`
service images.

## Objective

Ensure every service image carries the build identity operators and release reviewers need, ensure
each runtime-facing service exposes the same metadata through a standard endpoint, and make
immutable image release controls enforceable instead of implicit.

## Changes

1. Added `portfolio_common.build_metadata` with the canonical image metadata response shape.
2. Registered `GET /version` through `configure_standard_http_app`, covering API services and
   worker health web apps that use the Lotus standard FastAPI bootstrap.
3. Added OCI labels and matching runtime environment variables to all service Dockerfiles for Git
   commit SHA, Git branch, build timestamp, repo URL, image version, image digest, and CI pipeline
   run ID.
4. Updated `scripts/prebuild_ci_images.py` to pass the provenance build args from GitHub Actions,
   Git, or explicit `LOTUS_*` overrides.
5. Updated `scripts/write_build_provenance.py` so build evidence records the same metadata.
6. Added `.github/workflows/image-release.yml` as the CI-only immutable image publication lane:
   Git-SHA tags, GHCR push, BuildKit SBOM/provenance, CycloneDX SBOM artifacts, Trivy scan,
   Cosign signing, digest capture, and per-image release manifests.
7. Added `scripts/write_image_release_manifest.py` for digest, scan, signing, attestation,
   deploy-by-digest, same-image promotion, and runtime-env evidence.
8. Added `scripts/image_provenance_guard.py`, `make image-provenance-guard`, and wired the guard
   into `make architecture-guard`.
9. Updated README, operations runbooks, wiki source, validation/CI wiki source, and repo context.

## Behavior And Compatibility

This adds one operator endpoint, `GET /version`, to standard FastAPI service apps. It does not
change existing route paths, request DTOs, business response DTOs, database schema, Kafka payloads,
metrics, or service topology.

Local builds default `LOTUS_IMAGE_DIGEST` to `unknown` because a container image cannot know its
registry digest before the build/release lane resolves it. Release manifests record the resolved
digest, and Kubernetes deployment manifests must deploy by digest and inject the resolved digest
metadata when runtime `/version` parity is required.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/scripts/test_image_provenance_guard.py tests/unit/scripts/test_prebuild_ci_images.py -q`
2. `python -m pytest tests/unit/scripts/test_write_image_release_manifest.py tests/unit/test_ci_workflow_action_versions.py -q`
3. `python scripts/image_provenance_guard.py`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/build_metadata.py src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py scripts/prebuild_ci_images.py scripts/write_build_provenance.py scripts/write_image_release_manifest.py scripts/image_provenance_guard.py tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/scripts/test_image_provenance_guard.py tests/unit/scripts/test_prebuild_ci_images.py tests/unit/scripts/test_write_image_release_manifest.py --ignore E501,I001`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/build_metadata.py src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py scripts/prebuild_ci_images.py scripts/write_build_provenance.py scripts/write_image_release_manifest.py scripts/image_provenance_guard.py tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/scripts/test_image_provenance_guard.py tests/unit/scripts/test_prebuild_ci_images.py tests/unit/scripts/test_write_image_release_manifest.py`

## Documentation, Wiki, Context, And Skill Decision

Updated README, docs operations runbook, wiki Operations Runbook, wiki Validation and CI, repo
context, and review ledger because runtime/operator truth changed.

Wiki source changed and must be published after merge to `main`.

No platform skill source change is required. The durable lesson is enforced through
`make image-provenance-guard`, which blocks Dockerfile, CI build-arg, CI-only release workflow,
build-evidence, release-manifest, digest-deploy, no-build-secret, and `/version` drift.

## Remaining Work

PR CI should run the full architecture guard after this branch is opened. The first actual image
release workflow run should confirm GHCR permissions, Trivy availability, Cosign keyless signing,
and BuildKit SBOM/provenance attachment in GitHub Actions.
