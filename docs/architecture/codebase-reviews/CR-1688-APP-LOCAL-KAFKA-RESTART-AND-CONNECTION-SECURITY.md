# CR-1688: App-Local Kafka Restart And Connection Security

## Scope

- GitHub issues: #943 and #499
- Runtime owner: Core app-local Docker Compose
- Shared adapter owner: `portfolio_common.connection_security`

## Finding

The app-local broker used a fixed ZooKeeper broker identity without a restart policy. Recreating the
Kafka container immediately after interruption reproduced a deterministic fatal startup: the old
ZooKeeper session still owned `/brokers/ids/1`, so the new session received `NodeExistsException`
and exited. The same composition exposed development PostgreSQL credentials and plaintext Kafka,
while database and Kafka client construction did not centrally reject those local conveniences in
an unspecified or production-like environment.

## Decision

The app-local broker retries its unchanged process at most five times. ZooKeeper remains the owner
of ephemeral-session expiry; Core does not query, delete, or rewrite broker registration and does
not delete persistent data. A dedicated isolated gate verifies exact container ownership before
interruption, recovery, topic provisioning, two clean stop/start cycles, and a Kafka-dependent Core
service. Exhaustion returns a bounded operator diagnostic that directs investigation toward a live
competing broker and explicitly rejects volume deletion as default recovery.

Connection security is one shared infrastructure policy. Explicit local/dev/development/test
profiles may use the app-local password and plaintext broker. Any other or unspecified profile
rejects local/missing database credentials and plaintext Kafka before client construction. SSL and
SASL_SSL use explicit trust and secret-sourced SASL settings. Producers, consumers, admin clients,
health probes, and the transaction cutover client all consume the same policy. The unused Mongo
credential compatibility constants were removed after a repository-wide reference scan proved
that no runtime consumed them.

## Same-pattern review

The scoped search covered every direct `Producer`, `Consumer`, and `AdminClient` construction in
`src`, `tools`, and `scripts`; the operational offset-cutover client was the only bypass and was
aligned. All shared synchronous and asynchronous database URL paths now validate before engine
construction. No other Mongo runtime consumer exists. No API, OpenAPI, schema, migration, event,
topic identity, partition count, dependency, framework, or technology version changed.

## Evidence

- Pre-fix reproduction: recreated Kafka failed at `/brokers/ids/1` with old session
  `0x1000140fe700001` and new session `0x1000140fe700003`.
- Fixed live reproduction: the same interruption recovered healthy after two bounded retries in
  `21.456` seconds without deleting volumes.
- Repository-native gate: `make test-kafka-restart-recovery-gate` passed with isolated project
  `lotus-kafka-restart-broker-session-recovery-2d95ff5a`, two recovery retries, `21.257` seconds,
  topic creator exit `0`, two clean restart cycles, and healthy `ingestion_service`.
- Focused configuration, database, producer, consumer, admin, health, Compose-contract, gate,
  and operational-client tests passed with warnings treated as errors.

## Documentation and compatibility

The repository runbook, wiki source, and repository context define the explicit local exception,
production secret/trust inputs, safe recovery, and automated gate. This is a fail-closed
configuration hardening change outside local profiles and a restart-only local operability change;
product contracts and persisted business data are unchanged.
