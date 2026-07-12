# CR-1347 Image Digest Metadata Truthfulness

## Scope

Documentation and runtime metadata description cleanup for the image provenance contract.

## Objective

Keep the image provenance contract bank-buyable and technically truthful. The branch already
enforces Git-SHA image tags, build metadata, CI-only image push, SBOM, vulnerability scan, signing,
provenance attestation, release manifests, deploy-by-digest evidence, same-image promotion, and
`/version` metadata parity. This slice clarifies the one non-obvious boundary: the final registry
digest is resolved after push and cannot be truthfully embedded as a self-referential build-time
OCI label value because changing that label changes the image digest.

## Changes

1. Clarified README current-state wording for build-time labels versus post-push digest evidence.
2. Clarified the operations runbook and wiki source so `/version` digest parity is described as
   release/deployment metadata.
3. Clarified CR-1341 remaining-work/truth language for future reviewers.
4. Tightened the shared `BuildMetadataResponse.oci_labels` field description so the endpoint shape
   is presented as an OCI-label and release-metadata parity map, not a false self-digest claim.

## Behavior And Compatibility

No runtime behavior changed. `GET /version` keeps the same response shape. Dockerfiles, image
release workflow, release manifest schema, deployment topology, route paths, business DTOs, database
schema, Kafka contracts, and metric names are unchanged.

The implementation-backed contract remains:

1. build-time image metadata is embedded through OCI labels and runtime environment variables,
2. the resolved digest is captured after push in the release manifest,
3. deployment/runtime metadata supplies the resolved digest to `/version`,
4. Kubernetes deployment evidence must use digest references, and
5. the same digest reference is promoted across environments.

## Validation Evidence

Focused local validation:

1. `python scripts/image_provenance_guard.py`
2. `python -m pytest tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/scripts/test_image_provenance_guard.py tests/unit/scripts/test_write_image_release_manifest.py -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/build_metadata.py --ignore E501,I001`
4. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/build_metadata.py`
5. `make quality-wiki-docs-gate`
6. `git diff --check`

## Documentation, Wiki, Context, And Skill Decision

README, operations docs, wiki source, and CR evidence changed. Repo context did not need another
entry because the existing image provenance context remains correct at the current-state level.

No platform skill source change is required. The reusable lesson is already encoded in
`lotus-ci-enforcement-governance`; this slice keeps repo-local docs from overstating what OCI labels
can truthfully prove.
