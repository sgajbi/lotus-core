# CR-1574: Deterministic Spectral Toolchain

## Objective

Make the blocking OpenAPI Spectral gate reproducible, secure, and independent of mutable npm latest
tags while preserving every API contract and lint rule.

## Finding

`scripts/quality/openapi_spectral_gate.py` invoked unversioned `@stoplight/spectral-cli` through
`npx`. PR #771 therefore resolved a new dependency graph during CI. Under the governed Node 22
runtime, `@asyncapi/specs` `6.11.2` declared an ES module package while its entry point still used
CommonJS `module.exports`, causing `ReferenceError: module is not defined` before Spectral evaluated
any OpenAPI artifact.

The same clean-install failure was reproduced locally. OpenAPI generation, the Python quality gate,
and vocabulary validation were already green; no API defect caused the failure.

## Change

1. Added the dedicated `tools/api_governance/` package instead of placing Node files at the
   repository root or in a generic scripts folder.
2. Pinned current `@stoplight/spectral-cli` `6.16.1` exactly and committed its npm lockfile.
3. Overrode only `@asyncapi/specs` to compatible version `6.11.1`, preserving the current Spectral
   security release while excluding the broken transitive package contract.
4. Changed the Python gate to run `npm ci` with the tooling directory as its explicit working
   directory and then invoke the local cross-platform Spectral executable.
5. Ignored only the owned `node_modules` cache and retained the manifest and lock as source truth.
6. Added tests for exact versions, lock contents, clean-install arguments, Windows executable
   selection, local-binary invocation, workflow wiring, and absence of unversioned `npx` fallback.

## Similar-Pattern Review

A Core-owned source/workflow/Make scan found no other active `npx` quality-gate execution. The only
remaining Core reference is a negative regression assertion; CR-1170 now labels its original
`npx` wording as historical and superseded. Cross-repository prevention is tracked separately in
the platform governance backlog rather than being left in chat.

## Validation

- `make quality-openapi-spectral-gate` passed on Node `22.15.0` after a clean `npm ci`, generating
  all twelve current service artifacts with no result at `warn` or higher;
- `python -m pytest tests/unit/scripts/test_openapi_spectral_gate.py tests/unit/test_ci_workflow_action_versions.py -q` passed with `25` tests;
- `npm audit --audit-level=high` reported zero vulnerabilities;
- focused Ruff lint and format checks passed; and
- `git diff --check` passed.

## Compatibility

No API schema, route, example, event, database, runtime, domain, or downstream contract changed.
The Spectral ruleset and failure severity are unchanged. Only the tool acquisition and executable
path became deterministic.

## Documentation Decision

Repository context, current API-governance guidance, the review ledger, CR-1170 supersession truth,
and this review changed. README, OpenAPI artifacts, API inventory, supported features, migrations,
and wiki source require no change because product and operator-facing API behavior did not change.

## Follow-Up

Remove the `@asyncapi/specs` override only after the upstream package publishes a compatible release
and a clean lock passes Node 22, Spectral, npm audit, focused tests, and hosted API-governance CI.
