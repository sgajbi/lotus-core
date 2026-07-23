# CR-1652: Isolated Canonical Seed Proof

## Objective

Provide reproducible, branch-qualified Core evidence for GitHub issue
[#799](https://github.com/sgajbi/lotus-core/issues/799) without mutating a retained or unrelated
Docker runtime.

## Finding

The canonical seed contract had strong individual commands, but closure still required manual
composition. That left source provenance, shared image-build serialization, fresh-database proof,
dynamic Compose identity, stable convergence, retained-runtime identity, and evidence retention
dependent on operator discipline.

## Change

`scripts/validation/canonical_front_office_seed_proof.py` now:

1. accepts only a clean signed branch descended from `origin/main` at the exact public repository;
2. serializes exact-source image builds through the shared Git common-directory lock;
3. starts one generated dynamic-port Compose project and proves the database was empty;
4. runs the governed ingest-only seed without cleanup or reprocessing;
5. records contention during ingestion and requires stable database plus Core API projections;
6. rejects forbidden log signatures and non-zero pending or failed lifecycle state;
7. tears generated resources down to zero while proving the retained runtime's container, image,
   configuration, network, mount, volume, restart, state, and health identity did not change; and
8. writes exclusive, credential-free JSON evidence below `output/task-runs` and revalidates source
   commit, tree, branch, and cleanliness after teardown.

The driver cannot weaken canonical portfolio/date/project/Compose/prebuild/stability parameters
through CLI or configuration. Its reusable buildx cache also lives below the ignored evidence root;
prebuilding cannot create untracked source-root state that invalidates the final cleanliness proof.

## Same-Pattern Scan

The review covered canonical seed launchers, retained-runtime checks, output artifact writers,
Compose project naming, build locks, and source-provenance checks. Existing product bring-up remains
the Workbench-owned path; this driver is deliberately Core-only closure evidence.

## Validation

- 25 warning-strict driver tests passed.
- Ruff check and format verification passed.
- Strict no-incremental MyPy passed.
- Independent review completed with no findings.
- Signed implementation commit: `187b9120226e2b0bce9cdf0e298d7633ab461452`.

The governed Docker proof remains required at the final clean signed branch head.

## Compatibility And Documentation Decision

No API, OpenAPI, event, database schema, migration, calculation, or production topology changes.
Repository operations documentation changes because the branch-qualified proof command is new.
Wiki truth is unchanged for this Core-only diagnostic boundary.
