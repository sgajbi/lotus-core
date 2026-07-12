# CR-021 Docker Image Preflight and Local Runtime Drift Review

## Scope

Review local Docker-backed test/runtime tooling for avoidable failures caused by
missing base images or stale compose configuration.

## Findings

Two concrete issues remained after the earlier test-stack hardening:

1. `tests/test_support/docker_stack.py` still assumed required base images
   (notably `confluentinc/cp-zookeeper:7.5.0` and `confluentinc/cp-kafka:7.5.0`)
   were already available locally. When they were not, heavy integration/E2E
   runs failed late during compose bring-up instead of failing fast with a
   deterministic remediation path.
2. `docker-compose.yml` still mounted the removed
   `src/libs/financial-calculator-engine` path into `cost_calculator_service`
   even though CR-020 had already folded the remaining engine into the owning
   service. That mount was stale runtime debt.

## Actions Taken

1. Added Docker image preflight to the test harness:
   - parse compose images from `docker-compose.yml`
   - inspect whether each base image is present locally
   - pull missing images before compose bring-up
   - raise a clear `DockerStackError` if a pull fails
2. Added unit coverage for:
   - pulling missing images
   - explicit failure when pull fails
   - compose-up retry expectations after the new preflight step
3. Removed the stale `financial-calculator-engine` volume mount from
   `cost_calculator_service` in `docker-compose.yml`

## Result

Local heavy validation is less brittle:

- missing runtime images are handled up front instead of surfacing later as a
  noisy compose failure
- runtime configuration now matches the post-CR-020 service ownership model

## Follow-up

If Docker image sourcing becomes a broader concern later, add explicit image
mirror/pinning policy and cache warm-up to CI/dev bootstrap scripts. The local
runtime correctness gap reviewed here is now closed.
