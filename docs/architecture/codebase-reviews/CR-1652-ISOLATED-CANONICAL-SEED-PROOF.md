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
Compose container creation is not treated as runtime readiness. The driver gives transient
`created`, one-shot `running`, and healthcheck `starting` states one monotonic 180-second readiness
budget. Every Docker resource/inspect command is capped by the remaining budget, terminal
unhealthy, exit, restart, OOM, identity, or image failures take precedence across the complete
container set, and incomplete-resource diagnostics retain the observed resource projection.
The seed remains the directly owned subprocess for bounded timeout and teardown semantics. Before
launch, the driver builds a repository-fenced environment from the managed runtime variables and
proves that `portfolio_common` resolves inside this exact worktree. The direct child therefore
cannot resolve first-party code from an ambient editable checkout or fail merely because the
invoking shell lacks an inherited first-party `PYTHONPATH`.

## Same-Pattern Scan

The review covered canonical seed launchers, retained-runtime checks, output artifact writers,
Compose project naming, build locks, and source-provenance checks. Existing product bring-up remains
the Workbench-owned path; this driver is deliberately Core-only closure evidence.

## Validation

- 32 warning-strict driver tests and 9 repository-Python fence tests passed.
- Ruff check and format verification passed.
- Strict no-incremental MyPy passed.
- Independent review completed with no findings.
- Initial signed implementation commit: `187b9120226e2b0bce9cdf0e298d7633ab461452`.
- The first exact-head runtime attempt failed before seed while
  `portfolio_derived_state_service` was healthy at HTTP level but still in Docker's normal
  `starting` window. Artifact SHA-256:
  `276261816b949239629cc32c2ebb26d53af55db6f7ed9497ac44373ab88171b8`; runtime-log SHA-256:
  `95698f73d7d4e15b0c1f4b402f59607e74ebabf24c481c75f512b6d8f70b2c9b`. The generated project
  retained zero resources, retained-runtime identity was unchanged, and the source remained clean.
- The readiness-corrected exact-head attempt reached a healthy runtime and fresh 61-table database,
  then exposed a worktree-isolation defect before ingestion: the direct seed child could not import
  `portfolio_common`. Artifact SHA-256:
  `cdb4575ba18498a4ba35315c86d6da6a6b6d137e46789e0f616d8fcfbe236d31`.
  The generated project again retained zero resources, retained identity remained unchanged, and
  the runtime log contained no forbidden signatures. The direct seed child now receives a
  provenance-checked repository environment without introducing an unowned wrapper process.

The governed Docker proof remains required at the final clean signed branch head.

## Compatibility And Documentation Decision

No API, OpenAPI, event, database schema, migration, calculation, or production topology changes.
Repository operations and wiki source change because the canonical operator command must use the
repository Python fence outside this proof driver. No API or calculation documentation changes.
