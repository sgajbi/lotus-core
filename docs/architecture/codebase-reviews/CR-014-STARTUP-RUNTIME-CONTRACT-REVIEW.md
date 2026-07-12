# CR-014 Startup Runtime Contract Review

## Scope

Hot-path service startup/runtime behavior, with emphasis on services that own
write-ingress responsibilities or mandatory downstream dependencies.

## Findings

The main concrete defect found in this batch was in
`ingestion_service/app/main.py`.

- `ingestion_service` requires a Kafka producer to fulfill its core contract.
- Startup previously caught Kafka producer initialization failure, logged a
  fatal message, set `app_state["kafka_producer"] = None`, and still completed
  FastAPI startup.
- That behavior allowed a write-ingress service to advertise readiness while it
  was unable to perform its canonical publish path.

This is the wrong failure mode for a banking-grade ingress boundary. For this
service, Kafka producer initialization is not optional degraded behavior; it is
startup-critical.

## Actions taken

- Hardened `ingestion_service` startup to fail fast when Kafka producer
  initialization fails.
- Added lifecycle-level integration coverage that asserts startup raises on
  Kafka initialization failure.

## Rationale

Fail-fast startup is the correct contract here because:

- ingress correctness depends on successful durable publish
- serving requests without Kafka would create misleading readiness and operator
  confusion
- failing at startup is operationally simpler and safer than deferred runtime
  request failures against an already-advertised healthy service

## Evidence

- `src/services/ingestion_service/app/main.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`
