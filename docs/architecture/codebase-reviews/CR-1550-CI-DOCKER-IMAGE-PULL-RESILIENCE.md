# CR-1550 CI Docker Image Pull Resilience

## Objective

Resolve GitHub issue #726 by preventing a bounded transient registry failure from masquerading as a
transaction, integration, or E2E product failure while retaining fail-closed image acquisition.

## Finding

`tests.test_support.docker_stack.ensure_required_images_available` used one `docker pull` with no
subprocess timeout. It returned raw stderr on failure, could expose authentication material, and
classified neither transient registry failures nor permanent tag/auth failures. A repository scan
found no second direct `docker pull`; this helper is the shared acquisition boundary.

## Change

- Added immutable `DockerImagePullPolicy` with bounded attempts, timeout, exponential backoff, and
  jitter plus an inspectable maximum 367.2-second default budget.
- Classified timeout, rate-limit, and transient registry/network failures as retryable.
- Kept unknown, authentication, authorization, and missing-manifest failures permanent and
  fail-fast.
- Replaced raw stderr output with image, failure class, attempt, outcome, and elapsed diagnostics.
- Added controlled timeout-then-success, timeout exhaustion, permanent failure, classification,
  timeout propagation, jitter, and secret non-disclosure tests.

## Compatibility And Ownership

Production services, APIs, OpenAPI, financial calculations, persistence, Kafka contracts, and
runtime topology are unchanged. GitHub-hosted matrix cells have isolated Docker daemons, so no
cross-cell pre-pull was added. Existing BuildKit cache-backed prebuild remains the repo-built image
strategy; a future shared external-image strategy requires a governed registry mirror or
runner-level immutable cache.

## Validation

- `tests/unit/test_support/test_docker_stack.py`: `21 passed`.
- Scoped Ruff lint and format: passed.
- Same-pattern direct Docker-pull scan: only the governed helper and its tests remain.

## Durable Guidance Decision

Repository testing strategy, wiki validation guidance, and repository context changed. No central
skill, OpenAPI, migration, supported-feature, or platform-context change is required because the
existing resilience and CI governance already require bounded retry and truthful lane evidence.
