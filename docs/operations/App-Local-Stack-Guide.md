# App-Local Stack Guide

## Purpose

`lotus-core/docker-compose.yml` is the app-local and isolated-development stack for `lotus-core`.

It is intended for:

1. service-local development,
2. debugging `lotus-core` workflows in isolation,
3. app-local observability when platform-wide bring-up is not required.

It is not the canonical shared infrastructure baseline for the rest of Lotus.

Canonical shared infrastructure ownership lives in:

1. `lotus-platform/platform-stack`

## Ownership Boundary

`lotus-core` app-local stack keeps:

1. local Kafka / Postgres / Prometheus / Grafana overlays for isolated development,
2. `lotus-core` topic bootstrap,
3. `lotus-core` demo-data bootstrap,
4. `lotus-core` service-local debug convenience.

`lotus-platform/platform-stack` owns:

1. canonical shared Kafka broker lifecycle,
2. canonical shared Prometheus scrape baseline,
3. canonical shared Grafana provisioning,
4. canonical shared telemetry collector baseline.

## When To Use This Stack

Use `lotus-core/docker-compose.yml` when you want:

1. a fast app-local loop,
2. to debug `lotus-core` in isolation,
3. to validate app-local workflow behavior without the full platform.

Use `lotus-platform/platform-stack` when you want:

1. the canonical shared infrastructure baseline,
2. multi-app integration bring-up,
3. platform-level observability and governance alignment.

## Contract

The compose file now carries machine-readable ownership metadata:

1. project name: `lotus-core-app-local`
2. stack classification: `app-local`
3. canonical shared infra: `false`
4. canonical shared infra owner: `lotus-platform/platform-stack`

This contract is locked by tests in:

1. `tests/unit/test_app_local_observability_contract.py`
2. `tests/unit/test_app_local_stack_contract.py`
