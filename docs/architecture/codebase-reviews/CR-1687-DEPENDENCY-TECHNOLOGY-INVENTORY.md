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

The inventory generator records the reachable `origin/main` merge-base inspected when evidence is
refreshed. Exact lock and policy digests bind the decisive input content without introducing a
self-referential feature SHA that a rebase merge would rewrite. Execution receipts separately
record the exact checkout SHA. The generator is versioned `1.2.0` for this contract.

## Enforcement

`make dependency-technology-inventory`:

- validates fixed schema, inventory, repository, issue-owner, and generator identities;
- requires the source baseline to be a full SHA reachable from `origin/main`, so feature-only
  ancestry cannot masquerade as reviewed mainline provenance;
- requires a timezone-aware, non-future generation timestamp;
- recomputes component coverage and lock membership from all four governed closures;
- recomputes summary counts, certification decision, and technology state from the complete
  blocking posture, including classification, stale-review, yanked-release, and prerelease
  findings;
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
  future timestamps, feature-only baselines, ambiguous licenses, missing support authorities,
  contradictory release/review posture, and online authority drift;
- scoped Ruff format/check and MyPy;
- online deterministic refresh of all 104 components from exact PyPI release endpoints; and
- report-only guard result: structurally valid, 104 components, 120 blocking findings, zero
  production-ready or bank-buyable claim.

## 2026-08-20 cross-platform tooling-closure refresh

Scheduled mainline replay detected that the unconstrained Pygments dependency selected through
Pytest and Rich had advanced from `2.20.0` to `2.21.0` after the latter was published on
2026-08-17. The same deterministic replay failure was reproduced for both Linux/amd64 and
Windows/amd64; Windows merely failed first in the workflow. Issue #958 owns this review event.

The governed generators now retain `pygments==2.21.0` in both CI/build/test locks and refresh the
inventory from exact PyPI release evidence. Pygments remains a non-prerelease, non-yanked,
BSD-2-Clause CI-only component requiring Python 3.9 or newer. The inventory remains 104 unique
components with 88 approved license classifications, and all 104 components remain blocked or
supportability-review-required. The refresh also retains changed canonical metadata digests for
nine unchanged exact releases; it does not infer a package-version change or approval from mutable
upstream metadata.

This is the intended fail-closed review path for a newly selected transitive tooling release, not
resolver nondeterminism. Repeated clean platform replay must remain byte-identical after the
reviewed refresh. No application/runtime dependency, API/OpenAPI, database, migration, event,
calculation, Kafka, image, datastore, or topology contract changes. No README, supported-feature,
operator-runbook, wiki, central-context, or skill change is required.

## 2026-08-20 deterministic replay authority follow-through

Exact-main run `32387125286` failed after PR #965's identical Windows job had passed on the same
runner image and Python 3.11.9. The only generated difference was the newly published compatible
transitive `stevedore==5.9.1` replacing reviewed `5.9.0`. This falsified the earlier assumption that
pinning each observed drift individually made repeated replay deterministic: the generator still
resolved every unlisted transitive against mutable live package-index state.

Replay now uses pip-tools' documented existing-output behavior by seeding the temporary compiler
output from the committed platform lock. Fresh compilation remains unconstrained and is invoked
explicitly by `make compile-ci-tooling-lock`. The split keeps protected checks byte-stable while
retaining a deliberate dependency-update path whose full lock and technology-inventory diff must
be reviewed. Missing, stale, incompatible, or surplus committed pins still fail because pip-tools
reconstructs the closure from governed inputs before the byte comparison.

The fix preserves `stevedore==5.9.0`; no dependency or application/runtime contract changes. Unit
tests distinguish replay seeding from fresh update resolution, and repeated Windows plus Linux
replay checks provide platform evidence. The authored CI wiki changes because developer-facing
replay/update semantics changed; README, supported features, OpenAPI, migrations, and central
platform context remain unchanged.
