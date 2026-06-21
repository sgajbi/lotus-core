# CR-1123 Stable Compatible Dependency Refresh

Date: 2026-06-21

## Scope

Runtime, test, shared-runtime, and CI-tooling dependency manifests for `lotus-core`.

## Finding

The dependency surface was installable and recently CVE-remediated, but it was not current against
the latest stable compatible PyPI releases. The dependency-audit helper and runtime SBOM command
also still carried two explicit pip-audit vulnerability ignores even though the refreshed
third-party dependency set can pass without exceptions.

That combination creates avoidable audit ambiguity: a clean result should mean no known
third-party vulnerabilities, not a result hidden behind inherited ignore IDs.

FastAPI is intentionally held at `0.136.3` because `0.137.x` and `0.138.0` expose `_IncludedRouter`
objects that `prometheus-fastapi-instrumentator==8.0.0` cannot route-name safely. Integration-lite
is the compatibility signal for moving that pin.

## Action Taken

Updated the repo-managed pins across:

- root and service `pyproject.toml` manifests,
- `requirements/shared-runtime.in`,
- generated `requirements/shared-runtime.lock.txt`,
- `tests/requirements.txt`,
- `requirements/ci-tooling.lock.txt`,
- service-local support `requirements.txt` files.

Key compatible pins include:

- `fastapi==0.136.3`,
- `pydantic==2.13.4`,
- `uvicorn==0.49.0`,
- `SQLAlchemy==2.0.51`,
- `asyncpg==0.31.0`,
- `confluent-kafka==2.14.2`,
- `structlog==26.1.0`,
- `pytest==9.1.1`,
- `pytest-cov==7.1.0`,
- `hypothesis==6.155.7`,
- `ruff==0.15.18`,
- `mypy==2.1.0`,
- `pip-audit==2.10.1`.

The audit ignore list is now empty. Unit tests for the dependency-health and SBOM command builders
assert that no `--ignore-vuln` arguments are present unless a future slice explicitly reintroduces
one with documented evidence.

## Evidence

Dependency lock regeneration:

- `python scripts/update_shared_runtime_lock.py`
- Result: passed and regenerated `requirements/shared-runtime.in` plus
  `requirements/shared-runtime.lock.txt`

Install consistency proof:

- `make verify-dependencies`
- Result: passed with `No broken requirements found.`

Audit proof:

- `make security-audit`
- Result: passed with `No known vulnerabilities found.`
- Pip-audit skipped local editable Lotus packages because they are not published PyPI
  distributions. These skips are expected local-package audit behavior, not vulnerability ignores.

Runtime compatibility proof:

- `make test-integration-lite`
- Result: `121 passed` after rejecting `fastapi==0.138.0` due to the instrumentator
  `_IncludedRouter` route-name failure.

## Residual Risk

This slice does not claim full production or bank-buyable readiness. GitHub PR Merge Gate still
needs to prove the refreshed set on the Linux and Docker-backed lanes before merge. The FastAPI pin
should not move beyond `0.136.3` until `prometheus-fastapi-instrumentator` route-name compatibility
is proven by integration-lite. Future upstream vulnerabilities should be handled by fix-forward
upgrades or a documented compensating-control exception, not by silently carrying old ignore IDs.

## Bank-Buyable Control Movement

This slice improves:

- deterministic dependency installation proof,
- third-party vulnerability audit clarity,
- CI tooling version reproducibility,
- stale exception removal from both audit and SBOM generation paths.

It does not change API contracts, calculation behavior, persistence schema, or cross-app
integration contracts.

## Documentation And Wiki Decision

Repo-local README and wiki source were refreshed in the same branch to make dependency evidence,
validation commands, audience-specific entrypoints, and current capability boundaries easier to
find. The authored wiki source remains under `wiki/`; GitHub wiki publication is a post-merge sync
step, not a separate hand-edited truth source.
