# CR-1716: Auto-Merge And Exact-Main Releasability Authority

## Finding

The PR auto-merge workflow held write permissions and used `github.token`. A merge performed by
that actor can suppress the workflow events that produce post-merge release evidence. Core also had
no merged-PR dispatcher, while Main Releasability could run independently on `push` or schedule
without an immutable expected-revision contract.

## Decision

- Keep `automerge` as an explicit label-controlled opt-in.
- Use only `LOTUS_AUTOMERGE_TOKEN` for the rebase-merge request; warn and stop when it is absent.
- Give the auto-merge workflow read-only repository permission.
- Dispatch Main Releasability after every merged PR through an immutable tag derived from
  `pull_request.merge_commit_sha`.
- Pass the merge SHA, PR number, and source branch to Main Releasability.
- Reject a checkout that differs from the expected SHA or is not reachable from `origin/main`
  before any release gate executes.
- Retain explicit operator dispatch for deliberate release and institutional sign-off runs.

## Scope

This changes CI merge authority and release-evidence lineage only. It does not change application
code, APIs, schemas, migrations, financial calculations, events, dependencies, images, or runtime
topology.

## Evidence

- Workflow regression tests cover permission, token, label, dispatcher, immutable-ref, exact-SHA,
  main-reachability, transitive job-gating, and source-branch contracts.
- The platform fleet validator reports no `lotus-core` auto-merge/releasability violation against
  this checkout. Remaining failures identify separately owned repositories.
- GitHub Feature Lane, PR Merge Gate, and the first dispatcher-created Main Releasability run provide
  protected and exact-main completion evidence.
