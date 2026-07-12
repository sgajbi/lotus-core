# CR-335: Digest-Pinned Images and Build Evidence

## Problem
The build path had been accelerated, but it still lacked two gold-standard controls:
- digest-pinned service base images
- first-class build evidence for the produced runtime stack

That meant image construction was faster, but not yet fully anchored to:
- an immutable base-image identity
- a reusable SBOM artifact
- a provenance manifest tying the image build to repo state and the runtime lock

## Why It Matters
For production-grade governance, performance improvements are not enough. The build also needs:
- immutable upstream base references
- auditable evidence for what was built
- traceability from image to source and runtime dependency lock

## Change
- Pinned service Dockerfiles to:
  - `python:3.11-slim-bookworm@sha256:97b0eafb29f5ebfba254be840115b2f3bc24ff6ff3de9b905e04b74ee7227ba6`
- Added `scripts/write_build_provenance.py`
- Updated CI Docker cache keys to track `requirements/shared-runtime.lock.txt`
- Added Docker-build evidence generation in CI:
  - CycloneDX SBOM from `requirements/shared-runtime.lock.txt`
  - provenance manifest for the representative query-service build
  - artifact upload for the build-evidence bundle
- Mirrored the reusable standard into `lotus-platform`

## Result
The image build path is now materially stronger:
- base images are pinned by digest
- build cache invalidation follows the runtime lock
- CI emits explicit SBOM and provenance artifacts instead of only “build passed”

This moves the build system closer to a gold-standard release posture rather than only a fast CI posture.
