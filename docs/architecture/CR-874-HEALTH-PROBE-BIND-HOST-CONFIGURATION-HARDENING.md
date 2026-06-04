# CR-874: Health Probe Bind-Host Configuration Hardening

Status: Hardened on 2026-06-02.

## Finding

After CR-873, Bandit still reported ten medium `B104` findings in worker consumer managers. Each
finding came from a local Uvicorn health-probe server using a hardcoded bind-all host literal.

Bind-all health probes can be valid inside containerized service runtimes, but the behavior should
be governed and configurable rather than duplicated as local literals across workers.

## Change

Added `portfolio_common.health_server.health_probe_bind_host()` and routed all worker consumer
manager Uvicorn health-probe servers through it.

The helper reads `LOTUS_CORE_HEALTH_PROBE_BIND_HOST` and falls back to the existing
container-compatible bind behavior when unset. This preserves local/container reachability while
giving operators a governed override for restricted runtimes.

The Bandit baseline is now clean: `python -m bandit -r src -c pyproject.toml` reports zero findings.

## Boundary Preserved

This change preserves:

1. existing worker health-probe ports,
2. container-compatible default binding,
3. consumer and dispatcher orchestration,
4. topic verification behavior,
5. API contracts,
6. database schema.

## Next Ratchet

Bandit is now ready to move from report-only quality evidence into an enforced quality-baseline
security gate.

## Wiki Decision

No repo-local `wiki/` source update is included. This is a security baseline cleanup and
configuration hardening recorded in the repo-local quality reports and architecture review ledger;
it does not change operator-facing runtime behavior.

## Validation

Local validation passed for the slice:

1. `python -m pytest tests\unit\libs\portfolio-common\test_health_server.py tests\unit\services\calculators\cashflow_calculator_service\unit\test_consumer_manager.py tests\unit\services\valuation_orchestrator_service\unit\test_valuation_orchestrator_consumer_manager_runtime.py -q`:
   8 passed,
2. `python -m bandit -r src -c pyproject.toml`: 0 findings,
3. hardcoded Python bind-host search over `src`: no Python source matches,
4. `make quality-ruff-gate`,
5. `make quality-ruff-format-gate`,
6. `make typecheck`,
7. `git diff --check`.
