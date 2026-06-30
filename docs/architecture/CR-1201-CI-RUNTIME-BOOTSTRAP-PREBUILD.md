# CR-1201 CI Runtime Bootstrap Prebuilds And E2E Diagnostics

Date: 2026-06-30

## Scope

Runtime CI gates that bring up the compose-backed `lotus-core` stack, including Docker smoke,
E2E smoke, latency, performance, failure-recovery, and institutional-completion gates.

## Finding

CI runtime gates prebuilt the application service images but did not consistently prebuild the
runtime bootstrap images that apply schema migrations and create Kafka topics:

- `migration-runner`
- `kafka-topic-creator`

This can create a split-brain local or cached runtime where app containers run current code while
bootstrap containers lag behind schema or topic expectations. The failure mode is noisy and slow:
API ingestion can succeed or partially succeed, but downstream consumers fail against missing
columns or missing bootstrap state, causing E2E assertions to time out far from the root cause.

The E2E smoke artifact path also captured compose logs after the pytest fixture had already torn
down the dynamic compose project, leaving insufficient evidence for runtime diagnosis.

## Action Taken

Introduced a shared `RUNTIME_BOOTSTRAP_SERVICES` service subset and required each runtime prebuild
group to include those services before app services.

Moved primary E2E compose-log capture into the pytest fixture teardown path through
`LOTUS_TESTS_COMPOSE_LOG_FILE`, before compose teardown, and widened the PR Merge Gate artifact path
to preserve the captured output directory.

## Behavior And Compatibility

Public API contracts are unchanged.

Intentional CI/runtime behavior change:

- runtime gate prebuild groups now build `kafka-topic-creator` and `migration-runner` alongside the
  app services they validate,
- E2E smoke keeps dynamic compose-project logs from the active fixture before teardown.

Expected impact:

- lower risk of stale migration/topic bootstrap images in cached CI or developer runs,
- faster diagnosis when runtime tests fail,
- slightly broader prebuild work for runtime gates, limited to the bootstrap images that those
  gates already depend on.

## Evidence

Focused tests added:

- `tests/unit/scripts/test_ci_service_sets.py`
- `tests/unit/scripts/test_prebuild_ci_images.py`
- `tests/unit/test_support/test_docker_stack.py`

Focused unit proof:

- `python -m pytest tests/unit/scripts/test_ci_service_sets.py tests/unit/scripts/test_prebuild_ci_images.py tests/unit/test_support/test_docker_stack.py -q`
- Result: `18 passed`

Focused static proof:

- `python -m ruff check scripts/ci_service_sets.py scripts/prebuild_ci_images.py tests/conftest.py tests/test_support/docker_stack.py tests/unit/scripts/test_ci_service_sets.py tests/unit/scripts/test_prebuild_ci_images.py tests/unit/test_support/test_docker_stack.py`
- Result: passed

Whitespace proof:

- `git diff --check`
- Result: passed

Repo-native CI governance proof:

- `make quality-ruff-format-gate`
- Result: passed
- `python scripts/migration_contract_check.py --mode alembic-sql`
- Result: passed
- `make quality-workflow-governance-gate`
- Result: passed
- `make quality-wiki-docs-gate`
- Result: passed

## Reusable Pattern

When a CI gate starts a runtime stack, prebuild schema, topic, and control-plane bootstrap images
as part of the same named service group as the app services. Do not rely on a stale local image tag
or a fallback compose build for one-shot bootstrap containers.

Runtime diagnostic artifacts should be captured while the owning fixture still controls the stack.
Post-teardown workflow-level log collection is only a fallback.

## Documentation And Wiki Decision

Updated repository context because this is durable repo-local CI and runtime guidance.

No wiki source update is required. This changes internal CI reliability and diagnostic capture, not
operator-facing product behavior, API shape, or supported-feature claims.
