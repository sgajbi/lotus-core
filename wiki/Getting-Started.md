# Getting Started

Use this page when you are setting up `lotus-core` for development, validation, or a demo-support
slice. For business capability orientation, start with [Supported Features](Supported-Features).

## Prerequisites

- Python 3.11 or newer,
- Docker and Docker Compose,
- GNU Make or an equivalent shell that can run the repo `Makefile`,
- a sibling `lotus-platform` checkout when running platform-backed validators or wiki sync checks.

## First Local Setup

```bash
make install
cp .env.example .env
```

Then run the fastest repo-native confidence check:

```bash
make ci-local
```

`make ci-local` is the normal feature-lane parity command. It proves dependency consistency, lint,
typecheck, architecture, OpenAPI, warning budget, unit-db, integration-lite, and coverage posture
for the supported local slice.

## App-Level Evidence

Use the certification command when you need machine-readable proof that the supported core surface is
coherent:

```bash
make lotus-core-validate
```

The command writes evidence under `output/lotus-core-validation/`. A generated evidence file is only
useful when it reports a passing status for the runtime under review; do not treat the command name
as a readiness claim.

## App-Local Runtime

Use this path for isolated backend work:

```bash
docker compose up -d
python -m tools.kafka_setup
python -m alembic upgrade head
```

Then inspect the runtime:

```bash
docker compose ps
docker compose logs --tail=200 migration-runner
docker compose logs --tail=200 kafka-topic-creator
make test-docker-smoke
```

## Runtime Choice

- Use `lotus-core` app-local compose for isolated Core backend development.
- Use `lotus-platform/platform-stack` for shared infrastructure support.
- Use the governed `lotus-workbench` runtime when the task is populated front-office product proof.

## Common First Failures

| Symptom | First check |
| --- | --- |
| Dependency install or audit fails | `make verify-dependencies`, then `make security-audit` |
| Routes or OpenAPI drift | `make route-contract-family-guard` and `make openapi-gate` |
| Source-data product drift | `make source-data-product-contract-guard` |
| Runtime stack starts but APIs fail | [Operations Runbook](Operations-Runbook) startup checks |
| Downstream contract question | [API Surface](API-Surface), [Query Control Plane](Query-Control-Plane), and [Integrations](Integrations) |

## Where To Go Next

- [Development Workflow](Development-Workflow)
- [Validation and CI](Validation-and-CI)
- [Operations Runbook](Operations-Runbook)
- [Troubleshooting](Troubleshooting)
- [API Surface](API-Surface)
