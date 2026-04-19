# Overview

## Repository role

`lotus-core` is the system of record for portfolio, booking, account, holding, mandate, and
transaction data in Lotus.

## What it owns

- source-data ingestion and persistence
- foundational financial calculators
- position and valuation state
- position and portfolio time-series foundations
- operational read-plane contracts
- analytics-input, snapshot/simulation, support, lineage, and policy contracts

## What it does not own

- performance conclusions
- risk conclusions
- report composition
- advisory recommendation logic
- cross-cutting ecosystem platform narrative

## Why it matters

Downstream services depend on `lotus-core` for deterministic foundational truth.

That means:

1. ownership boundaries must stay explicit
2. source-data semantics must stay governed
3. supportability and replay behavior are part of the product contract
4. contract-family drift is an architectural defect, not just a documentation issue

## Current posture

- RFC-0082 governs downstream contract-family placement
- RFC-0083 governs target-state hardening
- local validation is heavier than most Lotus repos
- app-local isolated runtime is still supported
