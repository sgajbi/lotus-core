# Lotus Core Automation

Repository automation is organized by ownership. Use the Make targets as stable user-facing entry
points; Python module paths are implementation details governed with the repository.

## Script Areas

1. `development/` - local bootstrap, cleanup, and dependency-lock maintenance.
2. `generators/` - deterministic documentation and contract artifact generation.
3. `operations/` - production diagnostics, capacity profiles, recovery, reconciliation, and
   transaction cutover workflows.
4. `quality/` - architecture, API, contract, security, test, and CI quality gates.
5. `release/` - image build, exact-source CI image-set transport, SBOM, provenance, and
   release-manifest automation. `prebuild_ci_images.py` owns reusable local builds and timing
   evidence; `runtime_image_set.py` owns portable bundle creation, integrity manifests, load, and
   exact-source verification.
6. `validation/` - application certification and environment-backed validation.

## Naming Contract

1. Name files for the domain capability and action they own.
2. Do not use generic names such as `utils.py`, `helpers.py`, or `common.py`.
3. Do not use issue or RFC identifiers as filenames unless the script exclusively governs that
   issue/RFC lifecycle. RFC status and RFC-0083 closure guards are intentional examples.
4. Keep reusable logic in the narrowest owning module; do not create a new root-level script.
5. Add or update tests and Make targets when moving or extending executable automation.
