# CR-1339 Image Release Manifest Assertions

## Scope

Follow-up hardening for the image provenance release contract introduced in CR-1337.

## Objective

Make the release manifest writer fail closed when CI release evidence is incomplete or false,
instead of merely recording bad evidence. This reinforces the image release requirements for Git
SHA tagging, digest capture, SBOM, vulnerability scan, signing, provenance attestation,
digest-based Kubernetes deployment, and same-image promotion.

## Changes

1. Added release-evidence assertions to `scripts/write_image_release_manifest.py`.
2. Enforced that image tags end with the Git commit SHA and `image_version` matches the same SHA.
3. Enforced `sha256:` digest shape, `vulnerability_scan_status == "passed"`, SBOM evidence,
   signing evidence, provenance attestation evidence, digest-based Kubernetes deployment evidence,
   and at least one promotion environment.
4. Added focused tests for non-SHA tags, failed vulnerability scans, and missing supply-chain
   evidence booleans.

## Behavior And Compatibility

No runtime service behavior, API route, DTO, OpenAPI schema, database schema, Kafka contract,
metric, Dockerfile, Kubernetes manifest, or workflow trigger changed.

The release manifest script now rejects unsupported release evidence instead of producing a
misleading manifest. The CI image release workflow already passes the required values, so this is a
correctness and governance hardening change.

## Validation Evidence

Focused local validation:

1. `python scripts/image_provenance_guard.py`
2. `python -m pytest tests/unit/scripts/test_write_image_release_manifest.py tests/unit/scripts/test_image_provenance_guard.py tests/unit/libs/portfolio-common/test_build_metadata.py -q`
3. `python -m ruff check scripts/write_image_release_manifest.py tests/unit/scripts/test_write_image_release_manifest.py --ignore E501,I001`
4. `python -m ruff format --check scripts/write_image_release_manifest.py tests/unit/scripts/test_write_image_release_manifest.py`

## Documentation, Wiki, Context, And Skill Decision

No README, wiki, or context update is required because CR-1337 already documented the operator and
release contract. This slice only tightens manifest input validation.

No platform skill source change is required. The durable lesson remains enforced through
`make image-provenance-guard` and the manifest writer tests.

## Remaining Work

PR CI should run the full architecture guard and the image release workflow should be proven in
GitHub Actions on the first release candidate.
