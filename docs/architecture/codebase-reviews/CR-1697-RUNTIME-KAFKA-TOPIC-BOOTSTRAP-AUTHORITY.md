# CR-1697: Runtime Kafka Topic Bootstrap Authority

Date: 2026-08-21
Issue: #973
Status: merged and exact-main validated

## Objective

Ensure Kafka topic administration resolves its broker endpoint from the environment that is
authoritative when the client is constructed. Test bootstrap, host tools, and other runtime
initializers may establish that authority after Python modules have been imported.

## Finding

Main Releasability run `32430339688` at exact main
`47511d8df4e819d5229e6d518e54145205cb972c` failed in Integration Full after 1,130 tests passed.
`test_kafka_setup_ensures_topics_exist_and_is_idempotent` provisioned an isolated host-accessible
Kafka endpoint, but `tools.kafka_setup` retained the import-time Compose default `kafka:9093`.
The topic administrator exhausted ten retries on an unresolvable container hostname and exited.

The fixture was healthy: a directly constructed administration client used the runtime host
endpoint successfully. The defect was the lifetime of configuration authority, not Kafka broker
registration, topic idempotency, Docker cleanup, or runner capacity.

## Change

- `portfolio_common.config.load_kafka_bootstrap_servers` resolves the host override, ordinary
  bootstrap setting, or Compose default from the current environment.
- The topic-provisioning tool and shared Kafka administration helper call the loader immediately
  before client construction. The existing module constant remains as a compatibility snapshot
  for consumers whose environment is fixed before import.
- The provisioning factory also accepts an explicit broker endpoint for callers that already own
  a validated runtime authority.
- Connection-security validation remains centralized in
  `portfolio_common.connection_security`; endpoint selection does not bypass environment posture,
  TLS/SASL, or credential controls.

## Same-pattern review

The same stale import-time pattern existed in both Core-owned topic administration paths and was
removed from both. This slice does not convert unrelated long-lived service configuration: those
processes establish environment authority before application import and remain governed by their
existing typed settings and connection-security boundaries.

## Evidence

- Unit configuration and administration tests: `60 passed`.
- Formerly failing isolated integration test:
  `LOTUS_TEST_SCOPE=integration-all python -m pytest -q -W error tests/integration/tools/test_kafka_setup.py`
  -> `1 passed in 42.05s`.
- Scoped Ruff and MyPy validation passed for the changed Python sources.
- Signed exact feature head `6bc01707459a28ebcde3cb4c9b0fed8a86dfef18` passed Remote Feature
  Lane `32433993714` (6/6 jobs) and PR Merge Gate `32434065615` (23/23 jobs). Independent review
  approved endpoint/credential non-disclosure, runtime authority, security, and compatibility.
- PR #974 merged by governed rebase at exact main
  `577dba8ea08182355a262004937dd693fe46ac04`. Main Releasability run `32436643792` passed all 24
  executable jobs, including the formerly failing Integration Full topic-provisioning test, full
  E2E, coverage, exact-source image, performance, latency, and recovery lanes. The two institutional
  jobs were expected policy skips; there were no failures or cancellations.
- Wiki parity remains strict zero at published wiki head
  `9fa7545271bd490a6ac55aa6023f5a150b8e6229`; no wiki source change was required for this slice.
  Local and remote feature branches were removed after patch-equivalence proof, leaving one clean
  Core worktree on exact `main`.

## Compatibility and documentation decision

Kafka topic names, partition counts, idempotent topic creation, retry policy, security posture,
Compose topology, public APIs, OpenAPI, events, database schema, migrations, dependencies, and
operator commands are unchanged. Runtime endpoint selection changes only when authoritative
environment values change after import. No wiki change is required because operator workflow and
deployment topology did not change; this review and repository context record the engineering
invariant.
