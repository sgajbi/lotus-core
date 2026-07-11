# CR-1538: QCP External Hedge Posture Ownership

Date: 2026-07-12
Issues: #715, #465, #464
Status: Implemented locally; complete QCP package closure remains open

## Objective

Move six fail-closed external treasury and OMS source-posture products into complete Query Control
Plane ownership while simplifying their implementation and preserving every non-claim.

## Finding

QCP served external currency exposure, hedge policy, eligible hedge instruments, FX forward curves,
hedge execution readiness, and OMS acknowledgement posture through Query Service DTOs, six response
modules, a broad external-hedge facade, IntegrationService methods, and duplicate tests. No external
source was ingested, so the facade/repository-shaped design overstated runtime complexity.

## Implementation

- Added one QCP `external_hedge_posture` contract module and one application service for all six
  explicit source products.
- Reused the QCP effective-mandate port for portfolio-scoped posture and an injected clock for
  deterministic runtime metadata.
- Did not add a domain record, external client, repository port, or infrastructure adapter because
  no external treasury or OMS rows exist to read.
- Preserved each product's request/response fields, missing families, blocked capabilities, source
  system, contract version, unavailable reason, empty evidence collections, sorted fingerprint
  inputs, lineage, snapshot identity, and 404 behavior.
- Deleted the Query Service DTO blocks, seven service/facade modules, six IntegrationService
  methods, and duplicate tests. Preserved unrelated DPM-readiness and market-coverage compatibility
  exports that share the transitional DTO module.

## Domain And Cross-App Boundary

Core owns truthful source-availability posture and must fail closed while external evidence is not
ingested. Core does not price forwards, calculate treasury exposure, approve hedge policy, provide
hedge advice, determine product suitability, select counterparties, generate or route orders,
declare best execution, acknowledge OMS execution, certify fills/settlement, or perform autonomous
treasury or execution action.

## Compatibility

No public route, request/response field, schema component, product identity, unavailable reason,
blocked-capability list, lineage value, fingerprint scope, error mapping, database schema, or
runtime topology changed. `generated_at` now comes from the QCP runtime clock port instead of an
implicit metadata-helper clock while retaining the same UTC response contract.

## Validation

- Target application/router/integration cohort: `134 passed`.
- Full QCP unit/integration suite after retirement: `629 passed`.
- Full Query Service unit/integration suite after retirement: `1326 passed`.
- Query Service focused regression and test-manifest cohort: `85 passed`.
- Strict MyPy passed for the new contract and application modules.
- Ruff, architecture, source-product, API vocabulary/route-catalog, repository-output, and package
  contract gates passed.

## Measured Improvement

The target added two cohesive QCP modules and one focused test module. The retirement commit removed
`2,449` lines, seven Query Service service modules, six IntegrationService methods, six DTO
families, and six duplicate test modules. No unsupported source adapter or deployment boundary was
created.

## Remaining Hardening

Continue with QCP-owned DPM/reference, benchmark/market, and operations/support families. Advisory
simulation compatibility remains governed by #470. Split the integration router under #471 only
after the remaining application dependencies are QCP-owned.

## Documentation Decision

Updated repository context, current-state architecture, QCP wiki source, and review ledger. No
database-catalog change is needed because no external table exists. README and supported-feature
changes are unnecessary because public capability truth did not change. Existing skills already
cover fail-closed source posture, no-claim boundaries, layered ownership, async validation, and
same-pattern cleanup; no skill update is justified. Wiki publication remains post-merge.
