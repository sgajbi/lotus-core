# CR-1458: Combined Worker Health And Version Contract

Date: 2026-07-10
Issue: #468
Status: Hardened locally

## Objective

Prove the actual combined transaction-processing health app has a fail-closed dependency contract
and exposes the same governed build/image metadata required from its future container image.

## Contract Proof

The target app at `portfolio_transaction_processing_service.app.web` exposes:

- `/health/live` for lightweight process liveness;
- `/health/ready` for database, Kafka, and worker-runtime readiness;
- `/metrics` through the shared protected/internal scrape policy;
- `/version` through the shared build metadata contract.

The target-specific tests prove:

- readiness returns HTTP 200 only when `database`, `kafka`, and `worker_runtime` are all `ok`;
- readiness returns HTTP 503 when a consumer, dispatcher, or health-server task has failed even when
  database and Kafka remain reachable;
- runtime service identity is `portfolio_transaction_processing_service_web`;
- `/version` exactly equals the build block embedded in readiness;
- commit SHA, branch, UTC build timestamp, repository URL, image version, image digest, CI run ID,
  and matching OCI label map are all exposed;
- OpenAPI includes the four operational routes.

## Security And Supportability

Readiness exposes bounded dependency states, not raw exceptions or business identifiers. Build
metadata is source-safe and contains no credentials. Metrics access, trusted hosts, secure headers,
correlation, request identity, and trace propagation remain owned by the shared HTTP bootstrap.

## Compatibility

No runtime code or public business API changed. The target health app already used the shared
contract; this slice adds direct evidence before image and deployment activation. Existing calculator
health apps remain unchanged.

No README or wiki update is required because deployed topology and operational routes are unchanged.

## Validation

- target health/version contract tests: 2 passed;
- target transaction-processing unit pack: 60 passed;
- focused MyPy and Ruff passed;
- architecture docs and diff gates passed.
