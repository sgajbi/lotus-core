# CR-1654: E2E Test Value And Ownership Ledger

## Objective

Make E2E execution value, ownership, overlap, and lane placement reviewable and drift-resistant
without deleting or moving tests before equivalent proof exists.

## Finding

Exact collection at Core main identified 69 full E2E nodes across 25 modules and seven PR-smoke
nodes. None had node-level ownership identity, production defect class, lower-layer mapping,
runtime evidence, or non-duplication rationale. Twenty module-scoped scenario fixtures across 17
modules create setup-failure fanout, four polling implementations duplicate convergence behavior,
and three transaction-matrix nodes appear to belong at lower layers. The accounts risk matrix also
cited a full-only module together with the smoke target.

## Change

The versioned `e2e-test-value-ledger.v1.json` registers all 69 exact nodeids. Ten normalized
capability profiles own shared invariant, defect, fixture, dependency, contract, lower-layer, and
non-duplication evidence once; node entries contain stable identity, profile, current manifest
lanes, and review decision. This avoids a repeated 69-row documentation dump while preserving
machine-readable ownership.

`make e2e-test-value-guard` now:

1. collects the governed full and smoke suites without executing them;
2. enforces exact inventory and smoke-subset parity;
3. rejects duplicate ownership IDs or nodeids, invalid decisions, and lane drift;
4. requires every profile evidence field and verifies contract/proof paths exist;
5. requires every non-blocking decision to reference normalized reviewer/time/rationale, runtime,
   injected-fault, and impact evidence, with replacement proof for destructive decisions;
6. verifies Make/lint enforcement and the test-lane contract linkage; and
7. writes a deterministic count, digest, decision, and evidence-aware closure-blocker report below
   ignored output.

All 69 nodes initially remain `needs-review`, and the normalized review-evidence registry is empty.
That is an explicit closure blocker, not an assertion that every current node should remain.
Changing those strings without complete evidence cannot reduce the report's blocker count. No
runtime selection or test behavior changes in this slice. The risk matrix now truthfully maps its
full-only portfolio-query evidence to `make test-e2e-all`.

Runtime and fault records bind an exact repository-owned Actions run, source commit, and artifact
digest. Fault records additionally name the fault identity/injection, expected owning node, and
observed result. Arbitrary HTTPS URLs, shorthand run strings, and ordinary source paths are not
accepted as execution evidence.

The first PR execution exposed one same-pattern readiness defect: the complex lifecycle smoke node
waited for valuation output, then sampled control-plane publication readiness only once. It now
polls the control-plane endpoint through the shared bounded E2E client until publication controls
converge, retaining the last payload in timeout diagnostics. The scan found no other E2E assertion
that sampled `publish_allowed=true` without convergence.

## Validation

- E2E ledger guard: 69 full, seven smoke, ten profiles, zero findings.
- Eighteen warning-strict guard tests cover valid truth, missing/extra/duplicate nodes, invalid
  decisions, lane drift, missing evidence, weak rationale, evidence-free non-blocking decisions,
  incomplete runtime/fault/impact proof, unbound run identity, owning-node mismatch, smoke/full
  mismatch, and deterministic reporting.
- Ruff, format, strict MyPy, lane-governance, risk-matrix, documentation, and diff checks are
  required before commit.

## Compatibility And Documentation Decision

Production code, API/OpenAPI, events, database schema, migrations, and calculations are unchanged.
The complex-lifecycle smoke test now waits for the existing control-plane publication contract
instead of racing it. Repository context, testing strategy, and wiki source change because the
repository-native guard and review workflow are new. Publish the wiki source after merge and verify
strict parity before #729 closure.
