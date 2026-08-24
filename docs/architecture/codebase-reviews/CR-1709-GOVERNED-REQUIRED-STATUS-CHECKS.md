# CR-1709 Governed Required Status Checks

Date: 2026-08-23

Status: Fixed locally and live branch protection reconciled; protected PR refresh, exact-main
validation, wiki publication/parity, issue closure, and branch/worktree hygiene remain pending.

Issue: #999

## Finding

Branch protection required 18 contexts while Pull Request Merge Gate published five additional
blocking jobs/suites and Quality Baseline published 14 jobs named `... Gate`. Auto-merge therefore
could merge an exact head whose documented transaction, database-lifecycle, recovery, app-level,
import-boundary, security, dead-code, complexity, API-governance, or documentation gate was red.
Check names, documentation, local commands, and live enforcement were separate mutable truths.

## Financial-System Invariant

A protected merge is release evidence for a financial system of record. Every check described as
blocking must be technically non-bypassable for the exact source head, must be bound to the
expected check producer, and must remain reproducible from repository-owned authority. Advisory
evidence must be explicit and cannot be mistaken for release authorization.

## Design

1. `contracts/ci/required-status-checks.v1.json` owns strict mode, repository/branch identity,
   workflow policy, the one advisory context, and 37 sorted `(context, app_id)` requirements. The
   guard pins repository/branch authority to canonical `sgajbi/lotus-core` / `main`; manifest edits
   cannot redirect live certification to another protection target.
2. `required_status_checks_guard.py` validates the closed manifest shape, expands matrix suites,
   classifies every governed workflow job, requires blocking jobs and enforcement commands to be
   unconditional and fail-propagating, limits conditional checkout to the exact complementary
   `unit`/non-`unit` primary-repository pair over include-row matrices, requires alternate checkout
   to be unconditional, requires effective primary checkout before actionlint, permits other
   conditional auxiliary steps only for audited cache-save and artifact-upload actions, and
   requires every blocking job to retain exactly one
   unconditional executable `id: enforce` step on a non-auxiliary control, validates exact
   canonical PR keys without path filters and canonical merge-group triggers,
   accepts only include-row matrices with cell-identifying names, pins strict mode and the exact two
   governed workflow policies in code, requires every marked run control's effective shell to be
   exact `bash` and its script to be one bare invocation: one Make target, a governed matrix
   target, or the exact Windows lock-closure command. Shell operators, substitutions, quoting,
   redirection, multiple lines, Make flags, and wrapper commands fail closed. Referenced matrix
   targets are resolved from every include row and must each match the same bare target-name
   grammar, `[A-Za-z0-9_][A-Za-z0-9_.-]*`; assignments, options, paths, special-target syntax, and
   multi-target tokens fail closed. Every admitted static or resolved target must also be declared
   by GNU Make's delimited effective-database Files section evaluated with only fixed `PATH` and
   `LC_ALL=C`, and must appear in a literal static `.PHONY` declaration. Conditional directives,
   includes, declarations inside GNU Make column-zero-scoped `define` bodies, command-executing or file-mutating Make functions (`call`, `eval`, `shell`, `file`, and `guile`), native-extension `load`/`-load` directives, assignments absent from the exact repository-owned declaration inventory, target-specific assignments, `export`/`unexport`, `define`/`undefine`, non-recipe continuations, special execution targets in any target-list position, `vpath`, dynamic declarations, inherited process state (including `PATH`, Python startup/import variables, and loader variables), parse-time/recipe output,
   serialized variable bodies, ordinary files, undeclared rules, repeated effective-database target
   records, and missing Makefile authority fail
   closed. Every Make target referenced by a step in a blocking job must also own effective
   executable authority through its own recipe, a validated static phony prerequisite chain, or a
   statically named recursive-Make edge. Validation traverses that complete execution closure even
   when a parent also owns recipes. Every recipe in the closure uses a canonical direct identity:
   a repository Python script/module, one static recursive Make target, or an admitted Make
   precondition/diagnostic. Noncanonical expansions, nested interpreters, unquoted shell control
   operators, shell command substitutions, backticks, incomplete continuations, empty controls,
   and mutation or removal of governed execution variables fail closed. Continued physical recipes
   are reconstructed into their logical shell command before expansion, control-syntax, and
   command-identity validation, so a substitution token cannot be hidden across a continuation boundary.
   The target-bound `contracts/ci/governed-make-recipe-commands.v1.json` contract owns every
   admitted repository Python invocation, with or without arguments; unapproved modes,
   cross-target borrowing, missing authority, and stale entries fail
   closed against the full governed execution closure.
   Governed and unmanaged
   workflows are parsed and retained before GNU Make authority evaluation, so parse-time mutation
   cannot replace the workflow content being certified. The runtime image-set build therefore delegates its former inline shell body to
   `scripts/release/build_runtime_image_set.py`, which validates metadata and runs build then
   packaging under one timestamp with checked subprocess failure propagation. Dependency-health
   cache-key output is likewise serialized by the checked Python command instead of inline shell.
   Exact-source runtime image loading, local fallback, and verified-source receipt publication use
   `scripts/release/verify_runtime_image_set.py` as the final checked orchestration boundary.
   Artifact destinations must be literal expression-free paths below
   `output/`, so expression resolution cannot traverse into the checkout. Enforcement
   working-directory overrides fail closed. Every blocking `run` or `uses` step's effective
   workflow/job/step environment keys and exact values must match the positive governed inventory; alternate coverage bases, runtime-image
   identities, profiles, platform paths, and non-string values cannot weaken a blocking control.
   Pre-enforcement steps cannot mutate `GITHUB_ENV`/`GITHUB_PATH`, and actions are restricted to
   ten exact governed auxiliary or enforcement action references; setup-Python versions are pinned
   to the audited runner. Runtime-image verified state is bound directly to
   post-verification control steps instead of persisted through `GITHUB_ENV`. It requires blocking-job
   dependencies to be validated blocking jobs, inventories advisory producers in global
   context-uniqueness checks, and scans every
   repository workflow for static or dynamic required-context collisions, rejects unsupported
   job-name expressions, requires every manifest entry to bind to the exact GitHub Actions
   application ID `15368`, and compares exact sets. New, renamed, skipped, failure-tolerant,
   advisory-colliding, or impersonated jobs cannot silently authorize merge.
3. Live verification requires GitHub's app-bound `checks` response and a present `contexts` list
   set-equal to those check names. Missing, inconsistent, stale, wrong-app, malformed, or non-strict
   protection fails closed. The atomic PATCH still sends `contexts: []` to remove independent
   check-name-only authority; GitHub mirrors the app-bound names back in its GET response.
4. `make lint` now includes both import-boundary and manifest/workflow enforcement. The focused
   workflow-governance target includes mutation-style manifest tests. Manifest/model parsing,
   workflow traversal, effective Make target authority, Make execution-state policy, blocking-job execution policy, live GitHub protection, and CLI
   orchestration are separate owned
   modules; the same target runs scoped Ruff lint/format checks and hard-blocks Xenon complexity above `absolute C`, `module B`, or
   `average B` and Radon maintainability below rank B for the package, then applies scoped MyPy,
   Bandit, and Vulture checks before mutation tests with a 90% branch-aware coverage floor.
5. Main Releasability performs the live comparison read-only. Repository history (CR-1087) proves
   `github.token` lacks branch-protection read authority, so the workflow requires a dedicated
   fine-grained `LOTUS_BRANCH_PROTECTION_READ_TOKEN` with Administration read-only permission.
   A broad personal token is not an acceptable substitute.
6. Live branch protection is reconciled only after the exact PR head has posted and passed all 37
   checks. The guard's `--print-desired-protection` mode emits the exact atomic PATCH body, including
   an explicit empty legacy `contexts` array and the complete app-bound `checks` array. This avoids
   hand-copy drift, retained check-name-only authority, and making an absent context required before
   it has posted.
7. Both governed required-check workflows retain the canonical `pull_request` events for `main` and
   subscribe to `merge_group` for `main`; required contexts therefore post on both PR heads and the
   synthetic merge-queue commit instead of leaving branch protection waiting indefinitely.

## Meaningful Proof

Focused tests prove the repository manifest matches 37 expanded contexts, matrix values expand
deterministically, the advisory context must be both declared and observed, blocking jobs cannot
carry job-level conditions, conditional enforcement commands, or job/step failure tolerance;
only audited auxiliary actions may be conditional, and zero/duplicate/conditional/auxiliary/
non-executable `id: enforce` markers fail. Canonical PR and merge-group trigger mutations,
path-filtered PR triggers, unspecified/non-`bash` effective shells, non-strict manifests,
governed-workflow-set drift, and non-include matrix shapes fail before ambiguous or weakened checks
can be emitted. Shell-level failure-tolerance, dry-run, and background-execution escapes plus
dependencies on advisory or unknown jobs also fail. Exact `bash` supplies `pipefail`, while the
positive command grammar admits only one Make target, one governed matrix target, or the exact
Windows lock-closure command. It therefore rejects `||`, `!`, pipelines, substitutions,
conditions, redirects, multiple lines, Make options, assignments, and wrapper commands without an
open-ended shell denylist. Effective workflow/job/step environment injection through `MAKEFLAGS`,
`GNUMAKEFLAGS`, `MAKEFILES`, `MFLAGS`, or `BASH_ENV` remains independently prohibited. Every
admitted environment key is also pinned to its exact governed value, so `HEAD` cannot replace the
canonical changed-code coverage base and alternate runtime-image identities, profiles, or platform
paths fail before execution. The Docker
image-set producer's
multi-command implementation is owned by `make build-runtime-image-set`, so its marker is one bare
invocation. Matrix expressions are not trusted as unresolved text: every referenced include-row
value must match the same bare Make-target grammar, which excludes assignments, options, paths,
special-target syntax, and multi-target tokens. Static and resolved targets must also appear in an
active repository-root literal static `.PHONY:` declaration and GNU Make's delimited
effective-database Files section under a fixed minimal environment. Conditional directives, includes,
declarations inside GNU Make column-zero-scoped `define` bodies, command-executing or file-mutating Make functions (`call`, `eval`, `shell`, `file`, and `guile`), native-extension `load`/`-load` directives, assignments absent from the exact repository-owned declaration inventory, target-specific assignments, `export`/`unexport`, `define`/`undefine`, non-recipe continuations, special execution targets in any target-list position, `vpath`, dynamic declarations, inherited `MAKELEVEL`/`CI`/runner state (including `PATH`, Python startup/import variables, and loader variables), parse-time/recipe output,
serialized variable bodies, existing files, non-phony rules, and repeated effective-database target
records cannot authorize merge. The repository has no governed need for GNU Make double-colon rule
multiplicity. Artifact paths containing expressions fail before an action
can resolve them into a destination outside `output/`. The marker must run at repository root.
Pre-enforcement steps cannot write `GITHUB_ENV`/`GITHUB_PATH`; only governed action families are
accepted, every action step receives the same effective-environment validation as a run step,
action versions are exact rather than prefix-matched, setup-Python is runner-specific, and
runtime-image consumers carry verified state only on post-verification control steps.
Checkout-authority mutations prove that `if: false`, arbitrary conditions, incomplete pairs,
missing include rows, alternate-repository checkout, and checkout after actionlint cannot create a
green empty-workspace lint result. The only conditional checkout authority is the exact
complementary `unit`/non-`unit` pair, and every matrix branch must establish primary-repository
authority before actionlint enforcement.
The marker proves an explicitly declared fail-propagating control exists;
static validation cannot prove the command's business semantics, which remain code-review responsibility.
Advisory and blocking producers cannot
share one same-app context, and unmanaged static or dynamic workflow names cannot collide with a
required context. Non-GitHub-Actions manifest authority, noncanonical repository/branch targets,
advisory-as-required authority, and formatted or otherwise unsupported job-name expressions fail
before they can impersonate or redirect a required check. An undeclared new Gate fails before protection can drift, and live
parity rejects missing, stale, wrong-app, and wrong strict-mode authority. Workflow tests prove
import-boundary and required-check guards are reachable from `make lint`, and Main uses only the
dedicated read credential. The pre-remediation live guard characterized exactly 19 missing
contexts; after all 37 contexts passed on PR head `b4badf4f6`, branch protection was updated
atomically and live read-back passed with `strict=true`, `checks=37`.

Local feature-branch evidence:

- focused workflow/manifest pack after final review hardening: `503 passed`, with 94.11% branch-aware
  package coverage against a 90% hard floor;
- focused required-check guard file: `441 passed`, including disabled-checkout, exact complementary
  matrix checkout, alternate-repository non-authority, and actionlint ordering mutations;
- required-check code quality: Xenon maximum function C, maximum module B, average B; Radon
  maintainability is A for every owned module except the B-ranked workflow traversal module;
  scoped MyPy, Bandit, and
  Vulture passed;
- `make lint`: passed, including repository-wide Ruff/format, import-linter, the 37-check manifest
  guard, financial/data/security/contract guards, and no warning suppression;
- `make typecheck`: `Success: no issues found in 323 source files`;
- `make architecture-guard`: passed every governed application/domain/port/adapter boundary;
- `make quality-wiki-docs-gate`: passed;
- `make docs-evidence-pack`: passed with zero failed documentation checks while the authored docs
  delta was present.

## Compatibility And Scope

No runtime application, API/OpenAPI, event/Kafka, calculation, database schema/migration,
dependency, image, datastore, or topology contract changes. CI merge authorization intentionally
becomes stricter. Change-aware lane selection (#749), umbrella auto-close (#783), and promotion of
`Quality Baseline / Report Only` remain outside this issue.

## Skills And Context Decision

No central skill source is changed from the Core branch. `lotus-ci-enforcement-governance` already
requires repository-native guards, mutation proof, stable required-check policy, and fail-closed
validation. Core owns the immediate guard, tests, repository context, operator runbook, wiki source,
review note, and ledger. The reusable scaffold/validator gap for action-based enforcement is
durably assigned to `sgajbi/lotus-platform#723`, including primary-checkout authority, matrix
coverage, generator/template mutations, and proportional skill/context reconciliation.

## Pending Delivery Evidence

- dedicated fine-grained branch-protection read secret provisioned;
- exact-head Feature, Quality Baseline, and Pull Request Merge Gate green;
- refreshed exact-head Feature, Quality Baseline, and Pull Request Merge Gate green after final
  review hardening;
- protected merge and exact-main live-parity success;
- wiki publication and strict parity;
- #999 QA evidence/closure and merged branch/worktree removal.
