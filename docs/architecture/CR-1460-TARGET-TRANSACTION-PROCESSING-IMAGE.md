# CR-1460: Target Transaction Processing Image

Date: 2026-07-10
Issue: #468
Status: Hardened locally; release evidence pending

## Objective

Create one production-grade image package for the combined transaction-processing deployable and
enroll it in the governed CI-only image release lane without deploying it beside legacy workers.

## Packaging Defect Prevented

The three standalone calculator distributions expose overlapping top-level wheel packages such as
`core`, `consumers`, and `repositories`. Installing those wheels together can overwrite modules and
produce order-dependent imports even when the image build succeeds.

The target image therefore:

- builds one `portfolio-transaction-processing-service` wheel and `portfolio-common` wheel;
- copies only the required cost, cashflow, and position module roots under their current
  `src.services.calculators...` namespaces;
- does not install the three colliding legacy service wheels;
- does not copy the entire Core `src` tree;
- uses one pinned shared runtime lock and digest-pinned Python base;
- runs as non-root `appuser` and exposes only the combined worker port `8085`.

This bounded source closure is transitional. Surviving domain/application modules will move under
the target ownership tree before legacy roots are deleted.

## Image Provenance Contract

The Dockerfile carries OCI labels and runtime metadata for:

- Git commit SHA;
- Git branch;
- UTC build timestamp;
- repository URL;
- image version;
- image digest metadata slot;
- CI pipeline/run ID.

The target is added to:

- CI prebuild service inventory;
- CI-only image-release matrix;
- Python and Docker Dependabot coverage.

The existing governed release workflow tags by full Git SHA, pushes only in CI, resolves the pushed
digest, scans HIGH/CRITICAL vulnerabilities, exports CycloneDX SBOM, signs with Cosign, generates
BuildKit provenance, writes the digest release manifest, records digest-based Kubernetes policy and
`dev`/`uat`/`prod` same-image promotion, and uploads evidence. The target inherits those controls
through matrix enrollment.

An image cannot know its own content digest before publication. The build-time OCI/runtime slot is
therefore `unknown`; CI resolves the pushed digest into the release manifest and deployment supplies
that resolved digest to `/version`. No secret-like build ARG or ENV is present.

## Local Evidence

- image built successfully from a bounded 404 KB build context;
- final image runs as UID/GID `1000` (`appuser`);
- target manager imports and composes exactly the live and replay-request consumer groups/topics;
- unrelated `query_service` source is absent;
- OCI labels and runtime `build_metadata_payload()` match for commit, branch, timestamp, repo,
  version, digest slot, and run ID;
- target image/package, CI workflow, Dependabot, and provenance tests: 28 passed;
- image provenance guard and Ruff passed.

## Compatibility And Remaining Evidence

Compose/Kubernetes do not start this image yet. The three calculator images remain rollback/runtime
truth. This image must not run beside them.

No vulnerability-scan, signature, attestation, pushed digest, SBOM artifact, or same-image-promotion
result is claimed locally. Those become true only when the image-release workflow runs successfully
for the committed SHA. A target Kubernetes manifest must be added by digest during the atomic
deployment cutover.

No README/wiki change is required until the target image becomes current runtime truth.
