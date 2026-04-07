# RFC 085 - Advisory-Grade Canonical Simulation Execution for lotus-advise

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-04-05 |
| Last Updated | 2026-04-06 |
| Owners | lotus-core query-service + lotus-advise owners |
| Depends On | RFC 046A, RFC 058, RFC 067 |
| Related Standards | `lotus-platform/docs/architecture/canonical-simulation-authority-and-domain-evaluation-pattern.md` |
| Scope | Cross-repo |

## Executive Summary

`lotus-core` already owns canonical projected-state simulation for generic platform consumers, and `lotus-risk` already consumes that authority correctly.

`lotus-advise` still carries a local advisory simulation engine that duplicates too much of the projected-state execution layer. That is the wrong long-term ownership pattern.

This RFC upgrades `lotus-core` so it can execute canonical advisory simulation requests at the fidelity required by `lotus-advise`, using the proven advisory execution logic already implemented there. `lotus-advise` then delegates simulation execution to `lotus-core` after resolving canonical advisory context, while keeping advisory-only orchestration and lifecycle ownership local.

## Original Requested Requirements (Preserved)

This RFC introduces new requirements:

1. `lotus-core` must expose a canonical advisory simulation execution contract suitable for `lotus-advise`.
2. The execution path must preserve the advisory simulation semantics already proven in `lotus-advise`.
3. `lotus-advise` must run parity checks against the current local engine before cutover.
4. `lotus-advise` must delegate runtime simulation authority to `lotus-core` after parity is proven.
5. The cutover must not reduce advisory features, determinism, or replay evidence quality.

## Implementation Outcome

This RFC is implemented.

Delivered in `lotus-core`:

1. advisory-grade canonical simulation execution endpoint,
2. versioned advisory simulation contract governance through
   `X-Lotus-Contract-Version: advisory-simulation.v1`,
3. stable `application/problem+json` error taxonomy for contract mismatch, validation failure, and
   execution failure,
4. canonical lineage propagation including `lineage.simulation_contract_version`,
5. curated parity coverage against the advisory semantics previously proven in `lotus-advise`.

Delivered in `lotus-advise`:

1. runtime delegation to `lotus-core` as the normal simulation authority,
2. contract-version validation on the upstream simulation seam,
3. curated parity coverage across the old local oracle and the canonical `lotus-core` path,
4. controlled local fallback quarantined to non-production environments and retained only for
   migration safety and test-oracle use.

Closure result:

1. `lotus-core` is now the authoritative runtime owner of advisory simulation execution,
2. `lotus-advise` remains the owner of advisory APIs, context normalization, workflow semantics,
   lifecycle persistence, and advisory explainability,
3. local projected-state execution in `lotus-advise` is no longer a normal production authority.

## Problem Statement

Without this RFC:

1. `lotus-core` and `lotus-advise` risk diverging on projected-state semantics,
2. `lotus-risk` and `lotus-advise` will continue to consume different simulation authorities,
3. advisory workflows will remain harder to govern and replay consistently across the platform,
4. long-term maintenance cost stays higher because two engines must evolve in parallel.

## Decision

`lotus-core` becomes the runtime authority for canonical advisory simulation execution.

`lotus-advise` keeps ownership of:

1. advisory-facing APIs,
2. context resolution,
3. proposal/workspace lifecycle,
4. advisory decisioning and explainability,
5. downstream workflow and execution orchestration.

But `lotus-advise` no longer remains the default runtime executor of projected-state simulation math.

## Target Contract Shape

### Core-side execution contract

Add an advisory execution endpoint in `lotus-core` that accepts the canonical advisory simulation request already used inside `lotus-advise` after normalization and context resolution.

The contract is execution-oriented, not lifecycle-oriented.

Responsibilities:

1. execute advisory proposal simulation deterministically,
2. preserve request-hash and correlation lineage supplied by the caller,
3. return the canonical advisory simulation result contract.

### Advise-side usage model

`lotus-advise` continues to:

1. resolve `stateless` and `stateful` input modes,
2. compute canonical request hashes,
3. enforce idempotency and proposal lifecycle persistence,
4. call `lotus-core` to execute the simulation,
5. layer advisory workflow interpretation on top of the returned result.

## Reuse Strategy

The baseline advisory execution logic already exists and is proven in `lotus-advise`.

This RFC explicitly permits reuse of that implementation in `lotus-core` as the starting point, provided the result is:

1. brought under `lotus-core` ownership,
2. tested in `lotus-core`,
3. treated as canonical from the point of cutover.

The immediate goal is not elegant refactoring first. The immediate goal is correct ownership and runtime authority without feature loss.

After cutover, shared execution modules can be further rationalized if warranted.

## Requirement-to-Implementation Traceability

| Requirement | Target Implementation | Evidence Required |
| --- | --- | --- |
| Advisory execution endpoint in `lotus-core` | New control-plane or integration route backed by query-service advisory execution logic | router, DTOs, service, tests |
| Preserve advisory simulation semantics | Reuse and validate existing `lotus-advise` execution behavior | parity tests, golden scenarios |
| Preserve caller lineage | Request hash, correlation id, and optional idempotency metadata forwarded into result lineage | contract tests |
| `lotus-advise` delegates runtime execution | integration client in `lotus-advise` calling `lotus-core` | advise unit/integration tests |
| No feature loss at cutover | readiness, parity, and regression evidence for status/rules/gates/suitability outputs | golden and parity tests |

## Design Reasoning and Trade-offs

1. One simulation authority is more important than short-term implementation elegance.
2. Reusing the proven advisory engine first reduces cutover risk compared with re-inventing semantics in `lotus-core`.
3. Keeping `lotus-advise` as the API and workflow owner preserves clean product boundaries.
4. Temporary code duplication during migration is acceptable if it results in authoritative ownership and later runtime de-duplication.

Trade-off:

- The first cutover may involve copied or adapted advisory execution modules in `lotus-core` before a cleaner shared-library extraction exists. That is acceptable if governance, tests, and ownership become clearer overall.

## Delivery Slices

### Slice 1 - Core execution contract

1. Add advisory execution DTOs and route in `lotus-core`.
2. Bring advisory execution logic into `lotus-core` with targeted tests.
3. Preserve deterministic request-hash and lineage inputs.
4. Publish a versioned contract header and stable problem-details error taxonomy so downstream
   consumers can detect contract drift separately from execution failure.

#### Slice 1 delivery notes

The canonical contract for the execution endpoint is:

- Request header: `X-Lotus-Contract-Version: advisory-simulation.v1`
- Response header: `X-Lotus-Contract-Version: advisory-simulation.v1`
- Response lineage field: `lineage.simulation_contract_version = advisory-simulation.v1`

Slice 1 error taxonomy uses `application/problem+json` with stable error codes:

- `CANONICAL_SIMULATION_REQUEST_VALIDATION_FAILED`
- `CANONICAL_SIMULATION_CONTRACT_VERSION_MISMATCH`
- `CANONICAL_SIMULATION_EXECUTION_FAILED`

This contract shape is required before parity and cutover work because it gives `lotus-advise`
an explicit governance seam instead of an implicit best-effort integration.

### Slice 2 - Parity hardening

1. Add parity scenarios comparing current `lotus-advise` local execution with `lotus-core` execution.
2. Lock parity around status, intents, after-state totals, rule results, suitability, gate decisions, and lineage semantics.

#### Slice 2 delivery notes

Slice 2 should stay small and intentional. The parity gate is not “duplicate every engine test twice.”

The required parity suite is a curated scenario set that locks the semantics most likely to drift:

- FX funding and dependency ordering
- blocked missing-FX behavior
- reference-model drift outputs
- suitability-driven gate outcomes

Each scenario must normalize away transport-only noise and compare the business result shape:

- status
- execution intents and dependencies
- after-state totals, cash, and positions
- rule results
- gate decision summary
- suitability summary
- drift-analysis summary
- canonical lineage fields

### Slice 3 - Advise delegation cutover

1. Replace the current runtime simulation authority in `lotus-advise` with the `lotus-core` execution client.
2. Keep local execution only for controlled fallback or test-oracle use during migration.
3. Update capabilities and readiness language to reflect `lotus-core` authority.

### Slice 4 - Runtime authority closure

1. Make `lotus-core` the default and expected production authority.
2. Quarantine or retire the local advisory execution path so it is no longer the default runtime behavior.
3. Ensure docs and operational posture across repos reflect the cutover.

## Completion Assessment

The planned scope for this RFC is complete:

1. `lotus-core` exposes a tested advisory execution contract,
2. `lotus-advise` delegates runtime simulation execution to `lotus-core`,
3. parity scenarios cover the highest-risk advisory semantics that were previously duplicated,
4. the remaining local engine path is quarantined to non-production fallback and test-oracle use.

No additional implementation slice is required inside this RFC.

Any remaining work belongs to the follow-on platform hardening program for gold-standard canonical
simulation governance, lineage, parity policy, and duplicate-path retirement rather than to
RFC-085 itself.

## Test and Validation Evidence

Completion requires:

1. `lotus-core` unit and integration tests for advisory execution route and service,
2. `lotus-advise` parity tests covering local-versus-core execution semantics,
3. end-to-end tests proving advisory API behavior remains stable after delegation,
4. OpenAPI and vocabulary governance passing in affected repos.

## Original Acceptance Criteria Alignment

This RFC is complete when:

1. `lotus-core` exposes a tested advisory execution contract,
2. parity tests prove behavior equivalence for representative advisory scenarios,
3. `lotus-advise` delegates runtime simulation execution to `lotus-core`,
4. no advisory simulation feature is lost,
5. the platform has one authoritative simulation execution owner.

## Rollout and Backward Compatibility

1. `lotus-advise` public API remains stable.
2. The cutover is internal to the execution authority path.
3. Fallback behavior, if temporarily retained, must be explicit and non-default after parity is proven.

## Open Questions

1. Should the long-term shared execution logic remain in `lotus-core` directly or later move into a dedicated shared simulation package owned by `lotus-core`?
2. Should `lotus-risk` eventually consume the same advisory execution lineage metadata for scenario-linked analytics evidence?

## RFC-0020 Allocation Lens Baseline

RFC-0020 extends the implemented advisory simulation contract with canonical allocation-lens
governance before the Lotus apps are live. Because all callers remain controlled, the allocation
lens is additive to `advisory-simulation.v1`; RFC-0020 does not introduce
`advisory-simulation.v2`.

The proposal-facing allocation subset is intentionally front-office oriented:

1. `asset_class`
2. `currency`
3. `sector`
4. `country`
5. `region`
6. `product_type`
7. `rating`

Live reporting still supports issuer dimensions:

1. `issuer_id`
2. `issuer_name`
3. `ultimate_parent_issuer_id`
4. `ultimate_parent_issuer_name`

Those issuer dimensions remain available to live reporting, `lotus-risk` concentration analytics,
and future drill-down work. They are intentionally excluded from the RFC-0020 proposal allocation
API surface to avoid cluttering the advisor-facing before/after view.

Slice 1 of RFC-0020 adds a guarded contract map in code so changes to live reporting allocation
dimensions cannot silently drift away from advisory proposal allocation expectations.

Slice 2 extracts a shared `lotus-core` allocation calculator and routes both live reporting and
advisory simulation asset-class aggregation through it. Advisory simulation still retains
compatibility fields such as instrument allocation and shelf-attribute allocation until the
canonical allocation-lens response fields are introduced in RFC-0020 Slice 3.

The Slice 2 test baseline covers:

1. every live reporting allocation dimension in the shared calculator;
2. live reporting regression behavior after the calculator extraction;
3. advisory valuation parity against the shared calculator; and
4. no-op advisory before/after allocation parity for the shared calculator path.

Slice 3 adds canonical allocation-lens fields to `advisory-simulation.v1` without creating
`advisory-simulation.v2`:

1. `before.allocation_views`
2. `after_simulated.allocation_views`
3. top-level `allocation_lens`

The allocation views expose only the RFC-0020 proposal subset: `asset_class`, `currency`, `sector`,
`country`, `region`, `product_type`, and `rating`. Legacy allocation fields remain present for
compatibility while `lotus-advise` migrates callers to the canonical allocation-lens shape.

RFC-0020 Slice 6 closes the remaining live parity gaps for this contract:

1. stateful advisory requests now preserve the live classification metadata needed by the shared
   allocation calculator instead of collapsing non-asset-class dimensions into `UNCLASSIFIED`;
2. proposal cash allocation preserves per-currency rows instead of aggregating all cash into one
   base-currency bucket;
3. proposal allocation-view labels and weight precision now align with direct live reporting; and
4. the cross-service live parity validator passes against seeded portfolios with `lotus-core`,
   `lotus-risk`, and `lotus-advise` running together.

## Follow-on Work

1. Continue the platform-level hardening program for canonical simulation governance and duplicate
   path retirement under the newer gold-standard architecture RFCs.
2. Keep curated parity scenarios active as regression controls whenever advisory or canonical
   simulation semantics change.
3. Avoid reopening RFC-085 unless the canonical simulation contract itself changes materially.
