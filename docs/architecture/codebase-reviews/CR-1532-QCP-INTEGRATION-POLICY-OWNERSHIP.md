# CR-1532: Query-Control-Plane Integration Policy Ownership

Date: 2026-07-12
Issues: #715, #465
Status: Reconciled candidate; complete QCP integration-family closure remains open

## Objective

Move effective integration-policy contracts and resolution into QCP, remove policy/configuration
responsibility from Query Service, and preserve policy endpoint and Core snapshot governance
behavior.

## Finding

QCP owned `/integration/policy/effective` and used the same policy to gate Core snapshot sections,
but both paths called `IntegrationService.get_effective_policy(...)` from Query Service. The policy
module read Query Service environment settings directly and created wall-clock timestamps inside
application logic. Query Service retained policy/version and capability-override settings after
those public control-plane responsibilities had moved.

## Implementation

- Moved the effective policy response/provenance contract and policy resolver to QCP contracts and
  application packages.
- Added `IntegrationPolicyConfiguration` and `IntegrationPolicyService`; QCP dependency composition
  injects policy JSON, policy version, and `Clock`.
- Routed the policy endpoint and Core snapshot section governance through the QCP policy service.
- Removed effective-policy behavior from the broad Query Service integration facade and removed
  obsolete policy/version/capability settings from Query Service.
- Relocated policy tests to QCP and retained deterministic coverage for normalization, malformed
  policy fallback, global/tenant precedence, provenance, filtering, unrestricted requests, and
  generated timestamps.
- Extended the runtime-provider guard and application-port catalog to prevent direct wall-clock
  capability regression.

## Compatibility

No route, query parameter, response field, schema component, policy precedence, canonical consumer
mapping, section normalization/filtering, matched-rule identifier, warning, strict-mode behavior,
Core snapshot governance behavior, environment variable name, or runtime topology changed.

## Validation

- Combined QCP and affected Query Service regression cohort: `691 passed`.
- Query Service integration facade after policy-test relocation: `104 passed`.
- Query/QCP settings: `20 passed`.
- Strict scoped MyPy: seven source modules passed.
- Full QCP unit/integration suite: `578 passed`.
- Scoped Ruff, runtime-provider, application-port, strict architecture, application-layer,
  OpenAPI, source-product, vocabulary, and problem-details checks passed.
- Built QCP wheel imported `IntegrationPolicyService` and
  `EffectiveIntegrationPolicyResponse` from the installed `app` package.

## Remaining Hardening

QCP still imports the broad Query Service reference integration facade, reference contracts, and
repositories for non-policy integration source products. #715 and #465 remain in progress until
those families, operations/support, and advisory compatibility are resolved and clean-image proof
passes.

## Documentation Decision

Updated repository context, RFC-044, QCP wiki source, runtime-provider/application-port governance,
and the review ledger. No downstream migration note is required because the public contract is
unchanged. Stranded-truth reconciliation found only
`origin/fix/issue-699-clean-generated-artifacts`; its PR #703 is already merged, so the remote branch
is classified `delete` rather than a source of unique durable truth. The wiki check-only command
continues to report the known multi-page publication drift and must be rerun and published after the
eventual mainline merge.
