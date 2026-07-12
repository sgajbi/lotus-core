# CR-1202: GitHub Security Automation Coverage

## Objective

Use GitHub repository security features where they materially improve `lotus-core` production readiness without
weakening the governed CI model or creating noisy, unbounded dependency churn.

## Current Repository Security Posture

- Secret scanning is enabled.
- Secret scanning push protection is enabled.
- Open secret-scanning alerts were checked through the GitHub API and returned zero open alerts.
- Dependabot security updates are disabled in repository settings.
- Dependabot alerts are disabled in repository settings.
- Code scanning has no analysis configured yet.
- Secret scanning non-provider patterns and validity checks are disabled in repository settings.

## Decision

Add `.github/dependabot.yml` as the first low-risk security automation slice. The configuration covers:

- GitHub Actions workflow dependencies.
- Root, shared-library, service, calculator, and test Python dependency manifests.
- Runtime service Dockerfiles.

Each ecosystem is grouped and bounded with `open-pull-requests-limit` so the repository benefits from supply-chain
visibility without flooding the execution backlog.

Do not add CodeQL in this slice. Code scanning is valuable for `lotus-core`, but the current PR is already carrying a
runtime refactor and E2E stabilization workload. CodeQL should be enabled as a small follow-up slice or through GitHub
default setup after the current runtime gate is green, then governed with the same workflow timeout and non-blocking
rules used by the rest of the repository.

## Expected Improvement

- Dependency-update coverage becomes explicit and reviewable instead of relying on repository settings alone.
- New service dependency manifests and Dockerfiles fail a local governance test until Dependabot coverage is updated.
- Security automation is bounded to avoid PR churn that would reduce CI reliability or obscure defect-fix work.

## Validation Evidence

- `tests/unit/test_dependabot_security_coverage.py` enforces that every governed Python manifest and runtime Dockerfile
  has matching Dependabot coverage.
- GitHub API evidence confirmed that secret scanning is already enabled, push protection is already enabled, and there
  are zero open secret-scanning alerts at the time of this decision.

## Downstream Compatibility

No runtime behavior, API contract, event contract, database schema, or downstream response model changes.

## Remaining Admin Actions

Repository administrators should enable these settings in `sgajbi/lotus-core`:

- Dependabot alerts.
- Dependabot security updates.
- Code scanning, preferably GitHub default setup first unless a custom CodeQL workflow is required.
- Secret scanning non-provider patterns and validity checks if available for the repository plan.
