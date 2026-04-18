# Troubleshooting

## Common issues

### A route exists but you are unsure which service should own it

Use:

- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [Query Service And Control Plane Boundary](../docs/architecture/QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md)
- [API Surface](API-Surface)

### Shared runtime or ingress is broken

If the issue is shared infrastructure ownership, move to `lotus-platform` and its ingress/runtime
guidance.

### App-local stack started but services are still unhealthy

Check:

1. `docker compose ps`
2. `docker compose logs --tail=200 migration-runner`
3. `docker compose logs --tail=200 kafka-topic-creator`
4. `python -m alembic current`

### You need to diagnose portfolio processing state

Prefer support, lineage, replay, and reconciliation APIs before direct database inspection.

If runtime telemetry and database facts disagree, use durable database state as the source of truth
and record the rollout gap explicitly.

Start with:

- `GET /support/portfolios/{portfolio_id}/overview`
- `GET /support/portfolios/{portfolio_id}/readiness?as_of_date=YYYY-MM-DD`
- `GET /lineage/portfolios/{portfolio_id}/keys`

Then drill deeper into:

- replay evidence via `reprocessing-keys` and `reprocessing-jobs`
- valuation or aggregation backlog via the support job listings
- reconciliation blockage via `reconciliation-runs` and `findings`
- governed institutional validation via `GET /support/load-runs/{run_id}?business_date=YYYY-MM-DD`

### A control-plane route returns 400, 404, or 422 and you are unsure whether the problem is caller-side

Check the route family before changing code.

- `400` usually means request-shape, filter, or policy-evaluation problems
- `404` usually means the portfolio, session, run id, or job id genuinely does not exist in
  governed source state
- `422` on control-plane contracts often means the route exists but the requested source state
  cannot be fulfilled truthfully because dependencies or source data are missing

Use:

- [Query Control Plane](Query-Control-Plane)
- [Support and Lineage](Support-and-Lineage)
- [Architecture Index](../docs/architecture/README.md)

### Validation scope feels too expensive

Use targeted proof first:

- `python scripts/test_manifest.py --suite integration-lite --validate-only`
- `make test-unit-db`
- `make test-integration-lite`

Then move to GitHub-backed heavy validation for the full merge gate.

### Documentation looks like old PAS-era or ecosystem-level content

That material likely belongs in `lotus-platform`, not `lotus-core`.

See:

- `lotus-platform/wiki/Legacy-Core-Wiki-Migration-Ledger.md`

## Escalation rule

Stay in `lotus-core` when the problem is about:

- domain truth
- replay and persistence behavior
- source-data contracts
- supportability and lineage evidence
- route-family placement

Move to `lotus-platform` when the problem is about:

- shared ingress
- shared infrastructure ownership
- cross-repo runtime wiring
- ecosystem validation wrappers or platform governance automation

## Related pages

- [Operations Runbook](Operations-Runbook)
- [Support and Lineage](Support-and-Lineage)
- [Security and Governance](Security-and-Governance)
