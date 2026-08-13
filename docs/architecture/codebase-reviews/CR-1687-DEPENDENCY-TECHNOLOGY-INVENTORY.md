# CR-1687 Dependency Technology Inventory

## Objective

Advance #926 with deterministic, non-certifying license and supportability evidence for every
component in the governed runtime and CI/tooling lock closures. The evidence must fail closed when
its claims, component-derived summary, generator identity, repository authority, policy identity,
or source provenance contradict repository truth.

## Decision

The inventory is machine-generated from four platform-specific locks and exact PyPI release
metadata. PyPI proves publication metadata; it does not prove support, operational suitability, or
bank readiness. Support remains `review_required` until Technology Risk and Open Source Governance
records reviewed upstream support, vulnerability-disclosure, and lifecycle authorities.

The inventory generator records the latest committed revision of its governed lock and policy
inputs. This source revision remains reachable after a feature branch is rebased onto `main`.
Execution receipts separately record the exact checkout SHA, so input provenance and validation
execution provenance are both truthful. The generator is versioned `1.1.0` for this contract.

## Enforcement

`make dependency-technology-inventory`:

- validates fixed schema, inventory, repository, issue-owner, and generator identities;
- requires the source revision to be a full SHA reachable from the inspected checkout;
- requires a timezone-aware, non-future generation timestamp;
- recomputes component coverage and lock membership from all four governed closures;
- recomputes summary counts, certification decision, and technology state from component evidence;
- prohibits production-ready, bank-buyable, or popularity-based approval claims;
- validates policy-derived license classifications and support-review cadence; and
- emits an exact-execution receipt which remains blocked while findings exist.

`make dependency-technology-certify` additionally revalidates every exact PyPI response and still
returns non-zero unless all classifications are allowed. It is not used to turn missing human
support authority into an automated approval.

## Compatibility and documentation decision

This is CI/release governance only. No dependency version, base image, service, API/OpenAPI,
database, migration, event, calculation, Kafka, or runtime-topology contract changed. The testing
strategy, operator runbook, repository context, review ledger, and authored wiki carry the changed
release-evidence truth. No supported-feature or platform-wide context change is required.

## Validation

- focused generator and guard tests cover deterministic replay, prohibited claims, contradictory
  summaries, policy/lock drift, governed identity mutations, unreachable or malformed source SHAs,
  future timestamps, ambiguous licenses, missing support authorities, and online authority drift;
- scoped Ruff format/check and MyPy;
- online deterministic refresh of all 104 components from exact PyPI release endpoints; and
- report-only guard result: structurally valid, 104 components, 120 blocking findings, zero
  production-ready or bank-buyable claim.
