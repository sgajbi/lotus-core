# CR-331 Wheel-Based Runtime Image Fence

## Scope
Production service Dockerfiles for `lotus-core`.

## Finding
The service Dockerfiles were multi-stage, but they still copied source trees and builder-installed environments into the final images. That kept the runtime images closer to builder state than to a clean runtime-only install boundary.

## Fix
- Standardized all service Dockerfiles on a stronger wheel-based pattern:
  - runtime base with only runtime packages and venv
  - wheel-builder stage with build toolchain
  - final stage that installs only built wheels into the runtime venv
- Removed source-tree copying from final service images

## Evidence
- `docker build -f src/services/query_service/Dockerfile -t lotus-core-query-service-buildcheck .`
- `docker build -f src/services/valuation_orchestrator_service/Dockerfile -t lotus-core-valuation-orchestrator-buildcheck .`

## Follow-up
- If service framework drift is reduced later, move from shared constraints plus wheelhouses to fuller repo-level lock artifacts.
