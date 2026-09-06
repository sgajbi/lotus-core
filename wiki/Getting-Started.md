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

## Progressive Context Discovery

Before changing code or documentation:

1. read repo-root [`AGENTS.md`](https://github.com/sgajbi/lotus-core/blob/main/AGENTS.md) for the
   mandatory Lotus operating contract;
2. read the Platform
   [quickstart](https://github.com/sgajbi/lotus-platform/blob/main/context/LOTUS-QUICKSTART-CONTEXT.md)
   for ecosystem ownership;
3. read Core's
   [repository context](https://github.com/sgajbi/lotus-core/blob/main/REPOSITORY-ENGINEERING-CONTEXT.md)
   for financial invariants, architecture, task routes, and completion evidence;
4. use the Platform
   [skill routing map](https://github.com/sgajbi/lotus-platform/blob/main/context/LOTUS-SKILL-ROUTING-MAP.md)
   to load only the specialist guidance required by the task.

`CLAUDE.md` is a thin adapter to the same sources, not a second policy. Keep active issue, PR, and
blocker state in GitHub rather than adding it to durable repository context.

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

Use **3.12 locally** for ordinary work: it is the interpreter for the **in-process** gates — unit and
integration suites, coverage, lint, typecheck — so it is what reproduces those results.

Which interpreter actually runs your code depends on the gate:

| Gate style | Host interpreter | Code under test runs on |
| --- | --- | --- |
| In-process (`test-suites`, `coverage-gate`, quality gates) | 3.12 | **3.12** |
| Container (`docker-smoke-contract`, `e2e-smoke`, latency and performance gates) | 3.12 | **3.11**, inside the built runtime images |
| `windows-lock-closures` | 3.11 | dependency resolution only |

Two consequences worth knowing before you debug a failure:

- **A container-only failure will not reproduce under host 3.12.** Those lanes boot the real Compose
  stack from the 3.11 Dockerfiles, so 3.12 is only the orchestrator there. Reproduce them with the
  containers, not the host interpreter.
- **Reproducing the Windows dependency gate requires 3.11.** `windows-lock-closures` pins it
  deliberately so the closure it replays matches the runtime; replaying under 3.12 can resolve a
  *different* closure and disagree with the gate.

The in-process suites therefore run on an interpreter the runtime images do not use. That gap is
tracked as [#1046](https://github.com/sgajbi/lotus-core/issues/1046); it is not a setting to change
here.

## First Local Setup

Create an isolated Python 3.12 environment before `make install`. The bootstrap installs into the
interpreter that invokes it; it does not create or select a virtual environment for you.

Linux and macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python --version
make install
cp .env.example .env
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python --version
make install
Copy-Item .env.example .env
```

If Python 3.12 is managed by `uv` rather than registered with the Windows launcher, replace only
the first command with `uv venv --seed --python 3.12 .venv`. `--seed` is required because
`make install` invokes `python -m pip`; activation and every subsequent command stay the same. This
is an optional interpreter-management path, not a reason to install into a global environment.

`python --version` must report `3.12.x` before installation. A global interpreter, an already
populated environment, or packages inherited through `PYTHONPATH` are not valid bootstrap proof.

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

Use this path for isolated backend work after activating the environment created above:

```bash
docker compose up -d --build
```

Compose owns the startup ordering. `kafka-topic-creator` provisions the required topics through
`python -m tools.kafka_setup`; `migration-runner` applies `alembic upgrade head`; dependent services
start only after those one-shot containers exit successfully. Do not repeat either command against
the host network with container-only connection names.

Inspect that provisioning, migration, and service readiness all completed:

```bash
docker compose ps --all
docker compose logs --tail=200 migration-runner
docker compose logs --tail=200 kafka-topic-creator
curl --fail http://localhost:8200/health/ready
curl --fail http://localhost:8201/health/ready
curl --fail http://localhost:8202/health/ready
```

The two one-shot containers must show exit code `0`; each readiness request must return HTTP `200`.
Use `make test-docker-smoke` when the task requires the broader Docker contract rather than initial
setup proof.

## Clean-Checkout Proof

The documented path must be tested from a new clone, not inferred from a developer's existing
environment. Use a disposable checkout, confirm its Compose project has no containers, create the
virtual environment there, and execute [First Local Setup](#first-local-setup) followed by
[App-Local Runtime](#app-local-runtime). Before the run, clear inherited `PYTHONPATH` and verify the
selected interpreter and `docker compose ps --all` output.

Record the tested commit, operating system, Python version, Compose version, provisioning and
migration exit codes, readiness status codes, and teardown result on the owning GitHub issue or PR.
Do not put changing run identifiers or a delivery diary in this durable page.

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
