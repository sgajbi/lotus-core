# CR-846: Quality Baseline Governance Scaffold

Status: Hardened on 2026-06-02.

## Finding

The updated refactor objective requires measurable quality gates and a baseline before tightening
enterprise-readiness enforcement. `lotus-core` already had strong feature and PR gates, but it did
not have the requested repository-local quality baseline folder, portable report-only quality
workflow, `.importlinter` scaffold, `.spectral.yaml`, or top-level governance documentation set.

## Change

Added the initial report-only quality baseline and governance scaffold:

1. `quality/baseline_report.md`,
2. `quality/refactor_health_report.md`,
3. `quality/quality_scorecard.md`,
4. `quality/architecture_rules.md`,
5. `quality/api_governance_rules.md`,
6. `.github/workflows/quality-baseline.yml`,
7. `.importlinter`,
8. `.spectral.yaml`,
9. top-level architecture, API governance, observability, security, operations, and supported
   features documentation entrypoints.

The baseline records measured current-state evidence, including Python file/line counts, largest
files, Ruff findings, pytest collection posture, complexity posture, maintainability examples,
installed tool posture, and missing local tool posture.

## Boundary Preserved

This change does not alter:

1. runtime service behavior,
2. API routes or DTO fields,
3. database schema or migrations,
4. existing feature-lane or PR merge gate enforcement,
5. existing repository-native make targets.

## Wiki Decision

No repo-local `wiki/` source update is included in this slice. The change creates repository-local
quality and governance entrypoints and explicitly keeps the new CI path report-only. Wiki
publication should be considered after the quality baseline format stabilizes and before any
enterprise-readiness claim is made from these artifacts.

## Validation

Local validation passed for the slice:

1. focused pytest smoke,
2. Ruff check and format check over touched Python-adjacent files where applicable,
3. Alembic head check,
4. migration SQL contract smoke,
5. git diff whitespace checks,
6. stranded-truth reconciliation.
