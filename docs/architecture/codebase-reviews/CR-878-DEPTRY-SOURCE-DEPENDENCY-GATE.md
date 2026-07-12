# CR-878 Deptry Source Dependency Gate

Date: 2026-06-02

## Scope

Promote the scoped production-source dependency-usage baseline from CR-877 into a clean,
enforceable quality gate.

## Finding

CR-877 measured 928 `DEP003` findings because the root project metadata did not declare the shared
runtime dependency surface and deptry had no explicit first-party package model for the repository.
After adding the shared runtime dependency union and package/module mapping, the baseline collapsed
to runtime-only `DEP002` findings for dependencies that are required by packaging, migrations,
database drivers, or framework runtime behavior but not directly imported by production source.

## Decision

The root `pyproject.toml` now declares the shared runtime dependency union used by the service-local
packages and generated shared runtime lock. Deptry is configured with:

- first-party modules: `app`, `portfolio_common`, and `src`
- module-name maps for packages whose import name differs from the package name
- governed `DEP002` exceptions for runtime-only dependencies

The enforced production-source command is:

```powershell
python -m deptry src --extend-exclude "src/services/query_service/build" --extend-exclude ".*/tests/"
```

## Follow-Up

1. Keep `requirements/shared-runtime.in`, `requirements/shared-runtime.lock.txt`, service-local
   `pyproject.toml` files, and root dependency metadata synchronized when runtime dependencies
   change.
2. Continue treating `pip-audit` as the broader dependency-security baseline until dependency audit
   findings are clean or explicitly governed.
3. Revisit the governed `DEP002` runtime-only exception list if any listed dependency becomes
   unnecessary in service-local runtime packaging.

## Evidence

- `make quality-deptry-source-gate` => no dependency issues
- `make verify-dependencies` => no broken requirements found in the isolated dependency-health
  environment
- `.github/workflows/quality-baseline.yml` includes `deptry-source-gate`
- No wiki change: this is quality-gate and dependency metadata truth, not operator-facing product
  behavior.
