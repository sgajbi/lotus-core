# Getting Started

Use this page when you are setting up `lotus-core` for development, validation, or a demo-support
slice. For business capability orientation, start with [Supported Features](Supported-Features).

## Current Scope

This page covers a developer or support engineer's first local setup and repository-native evidence
path. It does not certify a production deployment, client demo, external dependency, or released
image; use [Validation and CI](Validation-and-CI) and the linked runbooks for those decisions.

| Need | Start Here | Evidence Boundary |
|---|---|---|
| Install and local confidence | [First Local Setup](#first-local-setup) | Local dependency and test evidence only. |
| Supported API/runtime proof | [App-Level Evidence](#app-level-evidence) | Deterministic supported-surface artifact, not production certification. |
| Isolated service diagnosis | [App-Local Runtime](#app-local-runtime) | Developer compose posture, not canonical front-office proof. |
| Product/demo runtime | [Runtime Choice](#runtime-choice) | Routes canonical proof to the governed Workbench flow. |

## Prerequisites

- Python 3.12 for local work — see the version note below,
- Docker and Docker Compose,
- GNU Make or an equivalent shell that can run the repo `Makefile`,
- a sibling `lotus-platform` checkout when running platform-backed validators or wiki sync checks.

**Python version, precisely.** Three different values are in play and the difference matters:

| Setting | Value | Where |
| --- | --- | --- |
| Declared floor | `>=3.11` | `pyproject.toml` |
| Behavioural and lint gates | `3.12` | `PYTHON_VERSION` in all five workflows; ruff `target-version = "py312"` |
| Windows lock-closure replay | `3.11` | the `windows-lock-closures` job in `feature-lane`, `pr-merge-gate`, `main-releasability` |
| Runtime images | `3.11` | all ten service `Dockerfile`s, digest-pinned |

Use **3.12 locally** for ordinary work: it is what every Linux behavioural and quality lane runs, so
it is what reproduces a gate result.

Two exceptions matter:

- **Reproducing the Windows dependency gates requires 3.11.** The `windows-lock-closures` job pins
  it deliberately so the closure it replays matches the runtime. Running those lock-replay commands
  under 3.12 can resolve a *different* closure and produce a result the gate will not agree with.
- **Released containers run 3.11**, so local and CI behaviour is not automatically proof of runtime
  behaviour.

The divergence between the behavioural gates and the runtime is tracked as
[#1046](https://github.com/sgajbi/lotus-core/issues/1046); it is not a setting to change here.

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
| Dependency cache appears stale or corrupt | Run `make verify-dependencies-clean`; inspect `output/dependency-health/clean-install-report.json` |
| External Docker image pull is transiently unavailable | Inspect the bounded `docker_image_pull_failed` attempt/failure-class diagnostics; permanent failures require correcting the image/tag/auth source |
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
