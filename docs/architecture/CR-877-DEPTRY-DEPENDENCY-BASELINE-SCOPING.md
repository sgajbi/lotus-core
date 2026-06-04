# CR-877 Deptry Dependency Baseline Scoping

Date: 2026-06-02

## Scope

Review the dependency-usage baseline for `lotus-core` and make the report-only CI signal truthful.

## Finding

The quality-baseline workflow previously ran:

```powershell
python -m deptry .
```

That command scanned local environment artifacts such as `.venv` when present in the checkout. It
also mixed production-source dependency findings with generated build output, making the result too
noisy for dependency governance.

The scoped production-source command is:

```powershell
python -m deptry src --extend-exclude "src/services/query_service/build"
```

Measured local baseline:

- scanned files: 485
- dependency issues: 928
- issue type: 928 `DEP003` transitive-dependency findings
- dominant modules: `portfolio_common`, `src`, `sqlalchemy`, `fastapi`, and `pydantic`

## Decision

Keep deptry report-only for now, but scope the workflow to production source and exclude generated
query-service build output. Do not promote deptry to an enforced gate until the repository metadata
declares the runtime dependency surface truthfully and first-party package/module ownership is
modeled cleanly.

## Follow-Up

1. Make root runtime dependency metadata reflect the shared production dependency surface.
2. Model first-party modules such as `portfolio_common` and service-local package roots explicitly.
3. Re-run the production-source deptry baseline and split remaining findings by real dependency
   hygiene issue versus package-boundary modeling issue.
4. Promote a clean or governed deptry source baseline into an enforceable quality gate.

## Evidence

- `python -m deptry src --extend-exclude "src/services/query_service/build"` => 928 findings
- `.github/workflows/quality-baseline.yml` dependency baseline now uses the scoped production-source
  command.
- No wiki change: this is quality evidence and CI scoping, not operator-facing product or runbook
  truth.
