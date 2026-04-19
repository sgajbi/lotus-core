# Getting Started

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git Bash on Windows

## Install

```bash
make install
cp .env.example .env
```

## Fast local proof

```bash
make ci-local
```

## App-local runtime

```bash
docker compose up -d
python -m tools.kafka_setup
python -m alembic upgrade head
```

## Important runtime choice

- use `lotus-core` app-local compose for isolated backend work
- use `lotus-platform/platform-stack` for shared infrastructure support
- use `lotus-workbench` canonical runtime when the real task is populated front-office product proof

## Where to look first

- [Operations Runbook](Operations-Runbook)
- [Troubleshooting](Troubleshooting)
- [API Surface](API-Surface)
