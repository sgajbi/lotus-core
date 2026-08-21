# CR-1705: Bounded Kafka startup recovery

Date: 2026-08-22
Issue: [#989](https://github.com/sgajbi/lotus-core/issues/989)
Status: Fixed locally; protected PR, exact-main, canonical Workbench, and wiki evidence pending

## Finding

Canonical front-office startup invokes Core with dependency-gated `docker compose up -d --build`.
The Kafka broker became healthy immediately after Compose exhausted its former ten health probes,
so Compose rejected `kafka-topic-creator` and aborted dependent Core startup even though the same
broker recovered seconds later. The existing restart gate started Kafka directly and polled health
outside Compose, so it did not certify this dependency boundary.

## Decision

Keep the existing broker command, `on-failure:5` restart policy, ZooKeeper state, and real
`kafka-topics` probe. Increase only the bounded health retry count from ten to twelve; the existing
30-second start period, 10-second interval, and five-second probe timeout remain unchanged.

The repository-native recovery gate now recreates `kafka-topic-creator` through its actual
`service_healthy` dependency after interrupting the broker. The gate rejects evidence unless the
real probe recovers within the Compose budget, topic creation succeeds, two clean restart cycles
remain healthy, and the dependent ingestion service becomes healthy. Failure diagnostics remain
bounded and explicitly reject destructive default remediation.

## Compatibility and boundaries

This is an app-local orchestration and validation change. It does not change production deployment
security, Kafka topics or partitions, event contracts, APIs or OpenAPI, database schema or
migrations, calculations, application dependencies, base images, or topology. Persistent Kafka
unavailability still becomes unhealthy and prevents dependent startup; no fixed sleep or readiness
bypass was added. Closed #943 remains the owner of stale broker-registration recovery. Bond quote
authority remains separate under #990.

## Evidence

- Compose contract unit tests pin the unchanged probe and the bounded 30s/10s/5s/12 posture.
- Recovery-driver and Compose contract tests bind the unique project, unchanged probe, bounded
  health policy, source-safe failure diagnostic, and exact topic-creator dependency path.
- Real managed Compose passed at exact signed `c28423349`: the interrupted broker recovered in
  `20.749s` with restart count `1`, topic creator exit code `0`, two clean restart cycles, and
  `ingestion_service=healthy`. Canonical Workbench startup, protected PR, exact-main, wiki
  publication, strict parity, issue closure, and branch/worktree hygiene remain pending at this
  fixed-local checkpoint.

## Documentation decision

The operator contract changed, so the repository runbook, authored Operations Runbook wiki, and
repository engineering context are updated in this slice. README, RFC, API, supported-feature,
migration, and central platform context truth do not change.
