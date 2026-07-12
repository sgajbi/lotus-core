# CR-1551 Dependency Health Content Cache

## Objective

Resolve GitHub issue #724 by preserving clean dependency installation proof while removing repeated
unchanged bootstrap cost from local, feature, PR, and same-job security-audit execution.

## Finding

Every dependency-health invocation created and deleted a fresh virtual environment, installed all
service distributions plus test/tooling requirements, and ran `pip check`. `make ci-local` and CI
then repeated the same bootstrap for security audit despite unchanged interpreter and manifests.

## Change

- Added a deterministic SHA-256 identity covering interpreter, platform, installer, root/service
  packaging manifests, dependency/test/tooling inputs, and cache implementation files.
- Added exact marker, interpreter, and `pip check` integrity checks.
- Build in disposable staging and publish only after successful installation and consistency proof.
- Added explicit `--no-cache`, cache/report overrides, and separate clean/audit JSON reports.
- Feature and PR workflows restore the ignored cache; main and scheduled releasability invoke the
  explicit clean target and upload both evidence files.
- Local main-parity execution expands the shared CI gate set directly from `ci-main` and starts with
  `verify-dependencies-clean`; it cannot inherit the cacheable `ci` dependency prerequisite.
- Added deterministic invalidation, corruption, interpreter/platform/installer, failure,
  bypass, audit, parallel-staging, marker, direct-CLI, report, and Make dependency-graph tests.

## Measurement

Local Windows evidence on 2026-07-12:

| Run | Result | Wall Time |
|---|---|---:|
| `make verify-dependencies-clean` | clean bypass, passed | `208.145s` |
| first unchanged `make verify-dependencies` | integrity-verified hit, passed | `1.756s` |
| second unchanged `make verify-dependencies` | integrity-verified hit, passed | `1.887s` |
| `make security-audit` | integrity-verified hit, no known vulnerabilities | `8.941s` |

Unchanged consistency-check wall time fell by 99.1%. This measures validation bootstrap only and is
not application runtime or production throughput evidence.

## Compatibility And Failure Posture

No API, OpenAPI, financial behavior, database, Kafka, service topology, or production runtime
contract changed. Any identity drift, missing interpreter, corrupt marker, failed `pip check`, or
failed install causes a clean miss or failure. Failed staging is removed and cannot become cache
truth. Main and scheduled lanes remain mandatory clean-install proof.

## Validation

- Cache identity and execution tests: `17 passed`.
- Workflow/cache evidence tests plus dependency tests: `37 passed`.
- Local main-parity dependency graph: `ci-main` resolves `verify-dependencies-clean` directly and
  does not depend on `ci`; the focused workflow-governance cohort passed `20` tests.
- Real clean, two-hit, and cached-audit commands: passed with measurements above.
- `make typecheck`: passed.
- Scoped Ruff lint/format and `git diff --check`: passed.

## Durable Guidance Decision

README, testing strategy, wiki source, repository context, CI workflows, Make targets, and review
ledger changed. No central skill or platform context change is required: existing Lotus CI skills
already require repo-native caching without weakening a dedicated clean lane.
